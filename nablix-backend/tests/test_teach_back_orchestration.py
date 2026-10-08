import asyncio
import base64
import json
import math
import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from websockets.legacy.client import connect

from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.core.exceptions import AdapterError, JourneyVersionConflict
from app.models.adapters import ConversationMessage
from app.models.teach_back import TeachBackPayload, TeachBackReply
from app.services import interaction_service
from app.ai_engine.teach_back import load_teach_back_config, teach_back_action
from app.ai_engine.prompt_registry import get_phase_block, load_prompt_registry
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
                response["phase_payload"]["orientation_bundle"]["target_micro_skill_ids"] = [payload["micro_skill_id"]]
                response["journey_state"]["phase_1_orientation"]["target_micro_skill_ids"] = [payload["micro_skill_id"]]
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

    async def forbidden_canvas(request: InteractionRequest) -> None:
        raise AssertionError("Teach-Back reached the numerical/OCR evidence pipeline.")

    monkeypatch.setattr(interaction_service, "_canvas_evidence_for", forbidden_canvas)
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
    understood = client.post("/interaction", json=submission(session_id, "TURN-001", "A number", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert understood.status_code == 200, understood.text
    for turn, message in (("TURN-002", "An object"), ("TURN-003", "Why?")):
        response = client.post("/interaction", json=submission(session_id, turn, message, "TEXT", "TEACH_BACK_SUBMISSION"))
        assert response.status_code == 200, response.text
        assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 1
    before_revisit = session_service._sessions[session_id]
    second_failure = client.post("/interaction", json=submission(session_id, "TURN-004", "An object", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert second_failure.status_code == 200, second_failure.text
    assert second_failure.json()["current_phase"] == "CONCEPT_ORIENTATION"
    assert session_service._sessions[session_id].attempt_count == before_revisit.attempt_count
    assert session_service._sessions[session_id].canvas_state == before_revisit.canvas_state
    assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 2
    revisit = client.post(f"/session/{session_id}/orientation/complete", json={"student_id": "ST001", "completed_video_ids": ["VID-KS3-T02-ORI"], "completed_worked_example_ids": ["WE-KS3-T02-01"]})
    assert revisit.status_code == 200, revisit.text
    assert revisit.json()["current_phase"] == "TEACH_BACK"
    assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 0
    assert session_service._sessions[session_id].teach_back_content.state.completed_micro_skill_ids == ["T02.M1"]
    assert session_service._sessions[session_id].teach_back_content.state.current_micro_skill_id == "T02.M2"


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


def test_missing_persisted_reply_keeps_recovery_pending(upstream: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = upstream["session_id"]
    original_post = student_model.post_json

    async def omit_reply(adapter_name: str, url: str, payload: dict[str, object], headers: dict[str, str], timeout_seconds: int, retry_count: int) -> dict[str, object]:
        response = await original_post(adapter_name, url, payload, headers, timeout_seconds, retry_count)
        response["phase_payload"]["teach_back"]["state"]["last_tutor_response"] = None
        return response

    monkeypatch.setattr(student_model, "post_json", omit_reply)
    failed = client.post("/interaction", json=submission(session_id, "TURN-001", "A number", "TEXT", "ANSWER_SUBMISSION"))
    assert failed.status_code == 503, failed.text
    session = session_service._sessions[session_id]
    assert session.pending_teach_back is not None
    assert session.last_processed_turn_id is None
    assert session.conversation_history == []
    assert upstream["engine_calls"] == 1


def test_orientation_waits_for_second_failure_receipt(upstream: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = upstream["session_id"]
    first = client.post("/interaction", json=submission(session_id, "TURN-001", "An object", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert first.status_code == 200, first.text
    original_store = interaction_service.store_teach_back_state

    async def interrupt_receipt(session: SessionRecord) -> SessionRecord:
        if "TURN-002" in session.teach_back_receipts:
            raise AdapterError("session_store", "Simulated unavailable receipt commit")
        return await original_store(session)

    monkeypatch.setattr(interaction_service, "store_teach_back_state", interrupt_receipt)
    interrupted = client.post("/interaction", json=submission(session_id, "TURN-002", "An object", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert interrupted.status_code == 503, interrupted.text
    stored = session_service._sessions[session_id]
    assert stored.current_phase == "CONCEPT_ORIENTATION" and stored.pending_teach_back.recorded
    session_service._sessions[session_id] = SessionRecord.model_validate(stored.model_dump(mode="json"))
    event_count = len(upstream["events"])
    start = client.post(f"/session/{session_id}/orientation/start", json={"student_id": "ST001"})
    completion = client.post(f"/session/{session_id}/orientation/complete", json={"student_id": "ST001", "completed_video_ids": ["VID-KS3-T02-ORI"], "completed_worked_example_ids": ["WE-KS3-T02-01"]})
    assert start.status_code == completion.status_code == 409
    assert len(upstream["events"]) == event_count
    monkeypatch.setattr(interaction_service, "store_teach_back_state", original_store)
    recovered = client.get(f"/session/{session_id}", params={"student_id": "ST001"})
    assert recovered.status_code == 200, recovered.text
    assert session_service._sessions[session_id].pending_teach_back is None
    assert "TURN-002" in session_service._sessions[session_id].teach_back_receipts
    assert upstream["engine_calls"] == 2


def realtime_result(session_id: str, turn: str, message: str, verdict: str | None) -> dict[str, object]:
    content = session_service._sessions[session_id].teach_back_content
    assert content is not None
    return {
        "interaction": {**submission(session_id, turn, message, "VOICE", "TEACH_BACK_SUBMISSION"), "question_id": None},
        "teach_back_id": content.teach_back_id,
        "micro_skill_id": content.state.current_micro_skill_id,
        "reply": {
            "evaluation": {"understanding_status": verdict, "misconception_detected": verdict == "MISCONCEPTION",
                           "error_code": "ERR-LETTER" if verdict == "MISCONCEPTION" else None,
                           "unmapped_misconception_description": None},
            "tutor_message": "A letter represents a number. Can you explain that?",
            "tutor_message_voice": "A letter represents a number. Can you explain that?",
            "next_action": teach_back_action(content, verdict),
        },
    }


def test_realtime_and_standard_share_progress_and_completion(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    first = client.post("/voice/teach-back/result", json=realtime_result(session_id, "TURN-001", "A number", "UNDERSTOOD"))
    assert first.status_code == 200, first.text
    assert upstream["engine_calls"] == 0
    context = client.post("/voice/teach-back/context", json={"session_id": session_id, "student_id": "ST001"})
    assert context.status_code == 200, context.text
    assert context.json()["micro_skill_id"] == "T02.M2"
    assert context.json()["instructions"].startswith(load_prompt_registry().layer_1_core)
    assert get_phase_block("TEACH_BACK") in context.json()["instructions"]
    second = client.post("/interaction", json={**submission(session_id, "TURN-002", "A number", "TEXT", "TEACH_BACK_SUBMISSION"), "question_id": None})
    assert second.status_code == 200, second.text
    assert second.json()["current_phase"] == "GUIDED_PRACTICE"
    assert upstream["engine_calls"] == 1
    assert [event["event_type"] for event in upstream["events"]][-2:] == ["TEACH_BACK_TURN_RECORDED", "TEACH_BACK_COMPLETED"]


def test_realtime_preserves_failure_limit_and_discussion(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    for turn, message, verdict in (("TURN-001", "An object", "MISCONCEPTION"),
                                   ("TURN-002", "Why?", None),
                                   ("TURN-003", "An object", "MISCONCEPTION")):
        response = client.post("/voice/teach-back/result", json=realtime_result(session_id, turn, message, verdict))
        assert response.status_code == 200, response.text
    assert response.json()["current_phase"] == "CONCEPT_ORIENTATION"
    assert session_service._sessions[session_id].teach_back_content.state.failed_explanation_count == 2
    assert upstream["engine_calls"] == 0


@pytest.mark.parametrize("message,confidence", [("okay", 0.9), ("Unclear", 0.1), ("", None)])
def test_realtime_input_checks_override_claimed_understanding(upstream: dict[str, object], message: str, confidence: float | None) -> None:
    session_id = upstream["session_id"]
    result = realtime_result(session_id, "TURN-001", message, "UNDERSTOOD")
    result["interaction"]["transcript_confidence"] = confidence
    response = client.post("/voice/teach-back/result", json=result)
    assert response.status_code == 200, response.text
    state = session_service._sessions[session_id].teach_back_content.state
    assert state.failed_explanation_count == 0 and state.completed_micro_skill_ids == []
    assert upstream["engine_calls"] == 0


@pytest.mark.parametrize("field,value", [("next_action", "MOVE_TO_PHASE_2"), ("tutor_message_voice", "T02.M1 is understood"),
                                          ("tutor_message", "Why? Can you explain?")])
def test_realtime_rejects_rule_breaking_replies(upstream: dict[str, object], field: str, value: str) -> None:
    session_id = upstream["session_id"]
    result = realtime_result(session_id, "TURN-001", "A number", "UNDERSTOOD")
    result["reply"][field] = value
    response = client.post("/voice/teach-back/result", json=result)
    assert response.status_code == 422, response.text
    assert session_service._sessions[session_id].teach_back_content.state.completed_micro_skill_ids == []
    assert upstream["engine_calls"] == 0


def test_realtime_lost_ack_recovers_and_duplicate_does_not_record_twice(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    result = realtime_result(session_id, "TURN-001", "A number", "UNDERSTOOD")
    upstream["fail_record"] = True
    failed = client.post("/voice/teach-back/result", json=result)
    assert failed.status_code == 503, failed.text
    assert client.get(f"/session/{session_id}", params={"student_id": "ST001"}).status_code == 200
    duplicate = client.post("/voice/teach-back/result", json=result)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "DUPLICATE_TURN"
    assert session_service._sessions[session_id].teach_back_content.state.completed_micro_skill_ids == ["T02.M1"]
    assert upstream["engine_calls"] == 0


def test_realtime_rejects_stale_target_canvas_and_unauthenticated_calls(upstream: dict[str, object]) -> None:
    session_id = upstream["session_id"]
    result = realtime_result(session_id, "TURN-001", "A number", "UNDERSTOOD")
    anonymous = TestClient(app).post("/voice/teach-back/result", json=result)
    assert anonymous.status_code == 401
    stale = client.post("/voice/teach-back/result", json={**result, "micro_skill_id": "T02.M2"})
    assert stale.status_code == 409
    result["interaction"]["canvas_snapshot_id"] = "SNAP-001"
    assert client.post("/voice/teach-back/result", json=result).status_code == 422
    assert upstream["engine_calls"] == 0


def test_live_realtime_teach_back_tool(upstream: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("NABLIX_RUN_REALTIME_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_REALTIME_SMOKE=true to run the billed Realtime smoke check.")
    key = os.getenv("NABLIX_OPENAI_API_KEY")
    if not key:
        pytest.fail("NABLIX_OPENAI_API_KEY is required for the live Realtime smoke check.")
    monkeypatch.setattr("app.services.teach_back_realtime.get_settings", lambda: Settings(openai_api_key=key))
    session_id = upstream["session_id"]
    started = client.post("/voice/teach-back/session", json={"session_id": session_id, "student_id": "ST001"})
    assert started.status_code == 200, started.text
    secret = started.json()["client_secret"]
    context = started.json()["context"]
    message = "A letter stands for a number we do not know yet."

    async def evaluate() -> tuple[str, float, TeachBackReply]:
        # Use the same configured model and short-lived credential as the browser.
        model = load_teach_back_config().realtime.model
        async with AsyncOpenAI(api_key=key) as audio_client:
            audio = await audio_client.audio.speech.create(
                model="gpt-4o-mini-tts", voice="alloy", input=message, response_format="pcm",
            )
        transcript: str | None = None
        confidence: float | None = None
        reply: TeachBackReply | None = None
        async with connect(f"wss://api.openai.com/v1/realtime?model={model}",
                           extra_headers={"Authorization": f"Bearer {secret}"}, open_timeout=20) as connection:
            await connection.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(audio.content).decode("ascii")}))
            await connection.send(json.dumps({"type": "input_audio_buffer.commit"}))
            async with asyncio.timeout(started.json()["response_timeout_seconds"]):
                async for raw in connection:
                    event = json.loads(raw)
                    if event["type"] == "error":
                        raise RuntimeError(f"Realtime rejected the smoke request: {event['error']}")
                    if event["type"] == "conversation.item.input_audio_transcription.completed":
                        transcript = event["transcript"]
                        probabilities = event["logprobs"]
                        assert probabilities
                        confidence = math.exp(sum(entry["logprob"] for entry in probabilities) / len(probabilities))
                        await connection.send(json.dumps({"type": "response.create"}))
                    if event["type"] == "response.function_call_arguments.done":
                        assert event["name"] == context["tool_name"]
                        reply = TeachBackReply.model_validate_json(event["arguments"])
                    if event["type"] == "response.done":
                        assert event["response"]["status"] == "completed"
                        assert transcript is not None and confidence is not None and reply is not None
                        return transcript, confidence, reply
        raise RuntimeError("Realtime closed without a Teach-Back tool result.")

    transcript, confidence, reply = asyncio.run(evaluate())
    assert "letter" in transcript.lower() and "number" in transcript.lower()
    assert reply.evaluation.understanding_status == "UNDERSTOOD"
    result = realtime_result(session_id, "TURN-001", transcript, "UNDERSTOOD")
    result["reply"] = reply.model_dump()
    result["interaction"]["transcript_confidence"] = confidence
    recorded = client.post("/voice/teach-back/result", json=result)
    assert recorded.status_code == 200, recorded.text
    assert session_service._sessions[session_id].teach_back_content.state.completed_micro_skill_ids == ["T02.M1"]
    assert upstream["engine_calls"] == 0


def test_disabling_realtime_preserves_standard_teachback(upstream: dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_teach_back_config()
    disabled = config.model_copy(update={"realtime": config.realtime.model_copy(update={"enabled": False})})
    monkeypatch.setattr("app.api.voice.load_teach_back_config", lambda: disabled)
    monkeypatch.setattr("app.services.teach_back_realtime.load_teach_back_config", lambda: disabled)
    session_id = upstream["session_id"]
    assert client.get("/voice/teach-back/options").json() == {"realtime_enabled": False}
    started = client.post("/voice/teach-back/session", json={"session_id": session_id, "student_id": "ST001"})
    assert started.status_code == 409
    result = client.post("/voice/teach-back/result", json=realtime_result(session_id, "TURN-001", "A number", "UNDERSTOOD"))
    assert result.status_code == 409
    standard = client.post("/interaction", json=submission(session_id, "TURN-001", "A number", "TEXT", "TEACH_BACK_SUBMISSION"))
    assert standard.status_code == 200, standard.text
    assert upstream["engine_calls"] == 1
