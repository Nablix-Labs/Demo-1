import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.core.exceptions import AdapterError, JourneyVersionConflict
from app.models.adapters import ConversationMessage
from app.models.teach_back import TeachBackPayload, TeachBackReply
from app.services import interaction_service
from app.ai_engine.teach_back import teach_back_action
from app.adapters import provider, student_model
from app.core.config import Settings
from app.main import app
from app.models.interaction import InteractionRequest
from app.models.session import SessionRecord
from app.services import session_service
from tests.test_session_events import _event_response
from tests.test_teach_back_engine import teach_back_content


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def teach_event(request_id: str, content: dict[str, object]) -> dict[str, object]:
    event = _event_response("WORKED_EXAMPLE_REQUESTED", request_id)
    event["phase_payload"] = {"phase": "PHASE_1_TEACH_BACK", "payload_type": "TEACH_BACK", "teach_back": deepcopy(content)}
    return event


@pytest.fixture
def teach_session(monkeypatch: pytest.MonkeyPatch) -> tuple[str, list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    settings = Settings(student_model_url="https://student-model.example", use_mock_student_model=False,
                        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"})

    async def post(adapter_name: str, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int, retry_count: int) -> dict[str, object]:
        events.append(deepcopy(payload))
        return teach_event(str(payload["request_id"]), teach_back_content())

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", post)
    response = client.post("/session/start", json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "VOICE"})
    assert response.status_code == 200, response.text
    return response.json()["session_id"], events


def test_open_and_refresh_hide_internal_content(teach_session: tuple[str, list[dict[str, object]]]) -> None:
    session_id, _ = teach_session
    response = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert response.status_code == 200, response.text
    view = response.json()
    assert view["current_phase"] == "TEACH_BACK"
    assert view["question_id"] is None
    assert "Unknown numbers" in view["message"]
    assert view["allow_text_input"] and view["allow_voice_input"]
    assert not any(view[key] for key in ("show_canvas", "show_hint_button", "show_visual_cue", "show_scaffold_panel"))
    assert "teach_back_content" not in view
    assert "teach_back" not in view["student_model_event"]["phase_payload"]
    stored = session_service._sessions[session_id]
    restored = SessionRecord.model_validate(stored.model_dump(mode="json"))
    assert restored.teach_back_content == stored.teach_back_content



@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch, teach_session: tuple[str, list[dict[str, object]]]) -> dict[str, object]:
    session_id, events = teach_session
    content = teach_back_content()
    content["state"]["status"] = "IN_PROGRESS"
    control = {"session_id": session_id, "events": events, "content": content, "engine_calls": 0,
               "fail_record": False, "fail_complete": False, "conflict_record": False, "discussion_action": "ASK_TEACH_BACK", "requests": {}, "version": 2}

    async def tutor(self: TutorEngineServiceAdapter, content: TeachBackPayload, student_input: str,
                    input_source: str, transcript_confidence: float | None, history: list[ConversationMessage]) -> TeachBackReply:
        control["engine_calls"] += 1
        verdict = None if student_input == "Why?" or transcript_confidence == 0.1 else "MISCONCEPTION" if student_input == "An object" else "UNDERSTOOD"
        return TeachBackReply.model_validate({
            "evaluation": {"understanding_status": verdict, "misconception_detected": verdict == "MISCONCEPTION",
                           "error_code": "ERR-LETTER" if verdict == "MISCONCEPTION" else None, "unmapped_misconception_description": None},
            "tutor_message": "A letter stands for a number. Can you explain that?", "tutor_message_voice": "A letter stands for a number. Can you explain that?",
            "next_action": teach_back_action(content, verdict) if verdict is not None else control["discussion_action"]})

    async def post(adapter_name: str, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int, retry_count: int) -> dict[str, object]:
        events.append(deepcopy(payload))
        key = payload["request_id"]
        if key in control["requests"]:
            saved_payload, response = control["requests"][key]
            assert payload == saved_payload
            return deepcopy(response)
        kind = payload["event_type"]
        state = content["state"]
        if kind == "TEACH_BACK_TURN_RECORDED" and control["conflict_record"]:
            control["conflict_record"] = False
            raise JourneyVersionConflict({"current_journey_state": {}})
        if kind == "TEACH_BACK_TURN_RECORDED":
            verdict = payload["evaluation"].get("understanding_status")
            if verdict == "UNDERSTOOD":
                state["completed_micro_skill_ids"].append(payload["micro_skill_id"])
                remaining = [skill for skill in state["target_micro_skill_ids"] if skill not in state["completed_micro_skill_ids"]]
                state["current_micro_skill_id"] = remaining[0] if remaining else None
                state["failed_explanation_count"] = 0
            elif verdict == "MISCONCEPTION":
                state["failed_explanation_count"] += 1
            state["last_tutor_response"] = {"tutor_response": payload["tutor_response"], "tutor_response_voice": payload["tutor_response_voice"],
                                           "tutor_next_action": payload["tutor_next_action"], "turn_id": payload["source_turn_id"]}
            response = teach_event(str(key), {"teach_back_id": content["teach_back_id"], "state": state})
            response["phase_payload"]["payload_type"] = "TEACH_BACK_STATE"
            if payload["tutor_next_action"] == "RETURN_TO_ORIENTATION":
                response = _event_response("WORKED_EXAMPLE_REQUESTED", str(key))
                response["phase_payload"]["teach_back"] = {"teach_back_id": content["teach_back_id"], "state": deepcopy(state)}
        elif kind == "TEACH_BACK_COMPLETED":
            if control["fail_complete"]:
                control["fail_complete"] = False
                raise AdapterError("student_model", "Simulated unavailable completion")
            assert payload["expected_journey_version"] == control["version"]
            response = _event_response("ORIENTATION_COMPLETED", str(key))
        elif kind == "ORIENTATION_COMPLETED":
            state["failed_explanation_count"] = 0
            response = teach_event(str(key), content)
        else:
            response = teach_event(str(key), content)
        control["version"] += 1
        response["journey_state"]["version"] = control["version"]
        control["requests"][key] = (deepcopy(payload), deepcopy(response))
        if control["fail_record"] and kind == "TEACH_BACK_TURN_RECORDED":
            control["fail_record"] = False
            raise AdapterError("student_model", "Simulated lost response")
        return response

    monkeypatch.setattr(TutorEngineServiceAdapter, "respond_to_teach_back", tutor)
    monkeypatch.setattr(student_model, "post_json", post)
    return control


def submission(session_id: str, turn: str, message: str, source: str, kind: str) -> dict[str, object]:
    return {"session_id": session_id, "student_id": "ST001", "interaction_type": kind, "input_source": source,
            "text_input": message if source == "TEXT" else None, "voice_transcript": message if source == "VOICE" else None,
            "transcript_final": True if source == "VOICE" else None, "transcript_confidence": 0.9,
            "turn_id": turn, "current_phase": "TEACH_BACK", "concept_id": "ALG_LINEAR_ONE_STEP", "hint_count": 0}


@pytest.mark.parametrize("kind,source", [(kind, source) for kind in ("TEACH_BACK_SUBMISSION", "ANSWER_SUBMISSION") for source in ("TEXT", "VOICE")])
def test_understanding_records_then_completes(upstream: dict[str, object], kind: str, source: str) -> None:
    session_id = upstream["session_id"]
    before = session_service._sessions[session_id]
    first = client.post("/interaction", json=submission(session_id, "TURN-001", "A number", source, kind))
    assert first.status_code == 200, first.text
    state = session_service._sessions[session_id].teach_back_content.state
    assert state.current_micro_skill_id == "T02.M2" and state.completed_micro_skill_ids == ["T02.M1"]
    second = client.post("/interaction", json=submission(session_id, "TURN-002", "A number", source, kind))
    assert second.status_code == 200, second.text
    assert second.json()["current_phase"] == "GUIDED_PRACTICE"
    assert [event["event_type"] for event in upstream["events"]][-2:] == ["TEACH_BACK_TURN_RECORDED", "TEACH_BACK_COMPLETED"]
    after = session_service._sessions[session_id]
    assert after.per_question_history == before.per_question_history
    assert after.hint_count == before.hint_count
    assert after.canvas_submissions == before.canvas_submissions


def test_lost_response_restart_and_changed_evidence(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    upstream["fail_record"] = True
    request = submission(session_id, "TURN-001", "A number", "TEXT", "ANSWER_SUBMISSION")
    failed = client.post("/interaction", json=request)
    assert failed.status_code == 503, failed.text
    snapshot = session_service._sessions[session_id].model_dump(mode="json")
    session_service._sessions[session_id] = SessionRecord.model_validate(snapshot)
    response = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert response.status_code == 200, response.text
    assert upstream["engine_calls"] == 1
    assert len(session_service._sessions[session_id].conversation_history) == 2
    duplicate = client.post("/interaction", json=request)
    assert duplicate.status_code == 200 and duplicate.json()["status"] == "DUPLICATE_TURN"
    changed = client.post("/interaction", json={**request, "text_input": "Different"})
    assert changed.status_code == 409
    assert upstream["engine_calls"] == 1


def test_completion_recovers_without_recording_or_evaluating_again(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    assert client.post("/interaction", json=submission(session_id, "TURN-001", "A number", "TEXT", "ANSWER_SUBMISSION")).status_code == 200
    upstream["fail_complete"] = True
    failed = client.post("/interaction", json=submission(session_id, "TURN-002", "A number", "TEXT", "ANSWER_SUBMISSION"))
    assert failed.status_code == 503, failed.text
    pending = session_service._sessions[session_id]
    assert pending.pending_teach_back.recorded and pending.pending_teach_back.completion_event is not None
    session_service._sessions[session_id] = SessionRecord.model_validate(pending.model_dump(mode="json"))
    blocked = client.post("/interaction", json=submission(session_id, "TURN-003", "A number", "TEXT", "ANSWER_SUBMISSION"))
    assert blocked.status_code == 409
    recovered = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["current_phase"] == "GUIDED_PRACTICE"
    assert upstream["engine_calls"] == 2
    assert len(session_service._sessions[session_id].conversation_history) == 4


def test_misconceptions_discussion_and_revisit(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    for turn, message in (("TURN-001", "An object"), ("TURN-002", "Why?")):
        response = client.post("/interaction", json=submission(session_id, turn, message, "TEXT", "TEACH_BACK_SUBMISSION"))
        assert response.status_code == 200, response.text
        assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 1
    second_failure = client.post("/interaction", json=submission(session_id, "TURN-003", "An object", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert second_failure.status_code == 200, second_failure.text
    assert second_failure.json()["current_phase"] == "CONCEPT_ORIENTATION"
    revisit = client.post(f"/session/{session_id}/orientation/complete", json={"student_id": "ST001", "completed_video_ids": ["VID-KS3-T02-ORI"], "completed_worked_example_ids": ["WE-KS3-T02-01"]})
    assert revisit.status_code == 200, revisit.text
    assert revisit.json()["current_phase"] == "TEACH_BACK"
    assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 0


@pytest.mark.parametrize("discussion_action", ["ASK_TEACH_BACK", "ASK_REEXPLANATION"])
def test_null_verdict_and_unclear_voice_preserve_progress(upstream: dict[str, object], discussion_action: str) -> None:
    session_id = upstream["session_id"]
    upstream["discussion_action"] = discussion_action
    before = session_service._sessions[session_id]
    request = submission(session_id, "TURN-001", "Unclear", "VOICE", "ANSWER_SUBMISSION")
    request["transcript_confidence"] = 0.1
    response = client.post("/interaction", json=request)
    assert response.status_code == 200, response.text
    after = session_service._sessions[session_id]
    assert after.teach_back_content.state.failed_explanation_count == before.teach_back_content.state.failed_explanation_count
    assert after.teach_back_content.state.completed_micro_skill_ids == before.teach_back_content.state.completed_micro_skill_ids
    assert after.attempt_count == before.attempt_count
    assert after.wrong_attempt_count == before.wrong_attempt_count
    assert after.canvas_state == before.canvas_state
    assert after.per_question_history == before.per_question_history
    assert after.student_model_state.mastery_status == before.student_model_state.mastery_status
    assert "ERR-LETTER" not in response.text


def test_stale_and_canvas_requests_do_not_evaluate(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    request = submission(session_id, "TURN-001", "A number", "TEXT", "TEACH_BACK_SUBMISSION")
    stale = client.post("/interaction", json={**request, "previous_tutor_turn_id": "TUTOR-stale"})
    assert stale.status_code == 409
    canvas = client.post("/canvas/submit", json={"session_id": session_id, "student_id": "ST001", "snapshot_data_url": "data:image/png;base64,aGVsbG8="})
    assert canvas.status_code == 409, canvas.text
    attached = client.post("/interaction", json={**request, "canvas_snapshot_id": "SNAPSHOT-001"})
    assert attached.status_code == 422
    assert upstream["engine_calls"] == 0
    assert session_service._sessions[session_id].canvas_submissions == []


def test_concurrent_duplicate_has_one_effect(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    request = InteractionRequest.model_validate(submission(session_id, "TURN-001", "A number", "TEXT", "ANSWER_SUBMISSION"))

    async def concurrent() -> None:
        first, second = await asyncio.gather(interaction_service.process_interaction(request, "test-token"),
                                             interaction_service.process_interaction(request, "test-token"))
        assert {first.status, second.status} == {"processed", "DUPLICATE_TURN"}

    asyncio.run(concurrent())
    assert upstream["engine_calls"] == 1
    assert len(session_service._sessions[session_id].conversation_history) == 2
    assert len(session_service._sessions[session_id].teach_back_receipts) == 1


def test_refused_version_rebases_pending_reply_without_engine_call(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    upstream["conflict_record"] = True
    response = client.post("/interaction", json=submission(session_id, "TURN-001", "A number", "TEXT", "ANSWER_SUBMISSION"))
    assert response.status_code == 409, response.text
    pending = session_service._sessions[session_id]
    assert pending.current_phase == "TEACH_BACK"
    assert pending.pending_teach_back is not None
    assert pending.pending_teach_back.turn_event.expected_journey_version == pending.student_model_event.journey_state.version
    recovered = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert recovered.status_code == 200, recovered.text
    assert upstream["engine_calls"] == 1
    assert session_service._sessions[session_id].teach_back_content.state.completed_micro_skill_ids == ["T02.M1"]


def test_diagnostic_orientation_and_exact_orientation_retry(teach_session: tuple[str, list[dict[str, object]]], monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, object]] = []

    async def post(adapter_name: str, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int, retry_count: int) -> dict[str, object]:
        events.append(deepcopy(payload))
        if payload["event_type"] == "ORIENTATION_COMPLETED":
            return teach_event(str(payload["request_id"]), teach_back_content())
        return _event_response(str(payload["event_type"]), str(payload["request_id"]))

    monkeypatch.setattr(student_model, "post_json", post)
    started = client.post("/session/start", json={"student_id": "ST001", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "VOICE"})
    session_id = started.json()["session_id"]
    completed = client.post(f"/session/{session_id}/diagnostic/complete", json={"student_id": "ST001", "answers": [{"question_id": "Q-T02-D01", "student_response": "A"}]})
    assert completed.status_code == 200, completed.text
    diagnostic = events[-1]
    assert diagnostic["diagnostic_run_id"]
    assert diagnostic["question_results"] == [{"question_id": "Q-T02-D01", "question_usage_id": "QU-T02-D01-P0", "result": "INCORRECT"}]
    for _ in range(2):
        response = client.post(f"/session/{session_id}/orientation/start", json={"student_id": "ST001"})
        assert response.status_code == 200, response.text
    assert events[-1] == events[-2]
    orientation = client.post(f"/session/{session_id}/orientation/complete", json={"student_id": "ST001", "completed_video_ids": ["VID-KS3-T02-ORI"], "completed_worked_example_ids": ["WE-KS3-T02-01"]})
    assert orientation.status_code == 200, orientation.text
    assert orientation.json()["current_phase"] == "TEACH_BACK"
    assert "Unknown numbers" in orientation.json()["message"]
