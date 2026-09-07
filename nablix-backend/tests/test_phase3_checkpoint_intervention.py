"""HTTP and persisted-state checks for the remediation boundary.

Assertions are written against the contract Numera-ui reads -- payload_type,
phase_payload.intervention_input_request, routing.next_action, status -- so a
rename that strands the frontend fails here rather than in a browser.
"""

import asyncio
from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.adapters.student_model import StudentModelServiceAdapter
from app.main import app
from app.models.remediation import (
    InterventionFeedback,
    InterventionVoiceInput,
    Phase3Checkpoint,
    StudentModelIntervention,
)
from app.models.session import SessionRecord, SessionResponse
from app.models.student_model_session import (
    InterventionInputSubmittedEvent,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service, session_store
from tests.test_session_events import _session_opened_response


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.fixture(autouse=True)
def isolated_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_service, "_interaction_locks", {})


def _event() -> StudentModelSessionEventResponse:
    event = StudentModelSessionEventResponse.model_validate(
        _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    )
    assert event.phase_payload is not None and event.phase_payload.question_set is not None
    question = event.phase_payload.question_set.questions[0]
    phase3 = event.journey_state.phase_3_independent_practice.model_copy(update={
        "current_question_id": question.question_id,
        "return_checkpoint": Phase3Checkpoint(
            topic_id=event.journey_state.topic_id,
            micro_skill_id=question.micro_skill_mappings[0].micro_skill_id,
            phase_visit_no=1,
            question_position_no=3,
            checkpoint_question_id=question.question_id,
            question_usage_id=question.question_usage_id,
        ),
    })
    return event.model_copy(update={"journey_state": event.journey_state.model_copy(update={
        "student_id": "ST440",
        "current_phase": "PHASE_3_INDEPENDENT_PRACTICE",
        "recommended_entry_phase": "PHASE_3_INDEPENDENT_PRACTICE",
        "phase_3_independent_practice": phase3,
    })})


def _terminal(event: StudentModelSessionEventResponse) -> StudentModelSessionEventResponse:
    checkpoint = event.journey_state.phase_3_independent_practice.return_checkpoint
    assert checkpoint is not None
    return event.model_copy(update={
        "phase_payload": None,
        "routing": event.routing.model_copy(update={
            "reason_code": "AUTOMATED_REMEDIATION_EXHAUSTED",
            "next_action": "COLLECT_INTERVENTION_INPUT",
        }),
        "journey_state": event.journey_state.model_copy(update={
            "intervention": StudentModelIntervention(
                intervention_id="INT-001",
                topic_id=event.journey_state.topic_id,
                micro_skill_id=checkpoint.micro_skill_id,
                reason_code="AUTOMATED_REMEDIATION_EXHAUSTED",
                state="ACTIVE",
            ),
        }),
    })


def _start(monkeypatch: pytest.MonkeyPatch, response: StudentModelSessionEventResponse) -> SessionRecord:
    async def send(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        assert access_token == "test-token"
        return response.model_copy(update={"request_id": event.request_id})

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    result = client.post("/session/start", json={
        "student_id": "ST440", "concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT",
    })
    assert result.status_code == 200, result.text
    return session_service._sessions[result.json()["session_id"]]


def _request(session: SessionRecord) -> dict[str, object]:
    """The TC-36 body, exactly as the frontend sends it over /interaction."""

    assert session.intervention is not None
    return {
        "session_id": session.session_id,
        "student_id": session.student_id,
        "interaction_type": "INTERVENTION_INPUT_SUBMITTED",
        "input_source": "CHOICE",
        "turn_id": "INTERVENTION-1",
        "current_phase": "INDEPENDENT_PRACTICE",
        "concept_id": session.concept_id,
        "question_id": "Q1",
        "hint_count": 0,
        "intervention_id": session.intervention.intervention_id,
        "topic_id": session.intervention.topic_id,
        "micro_skill_id": session.intervention.micro_skill_id,
        "selected_reason_codes": ["DONT_KNOW_HOW_TO_START"],
        "voice_input": {
            "provided": True,
            "audio_ref": None,
            "transcript": "I cannot choose the operation.",
        },
    }


def test_tc26_addendum_contract_normalizes_without_breaking_legacy_payloads() -> None:
    source = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
    question = source["phase_payload"]["question_set"]["questions"][0]
    source["journey_state"]["phase_3_independent_practice"].update({
        "current_question_id": question["question_id"],
        "return_checkpoint": None,
    })
    source["journey_state"]["return_checkpoint"] = {
        "topic_id": source["journey_state"]["topic_id"],
        "phase": "PHASE_3_INDEPENDENT_PRACTICE",
        "phase_visit_no": 3,
        "question_position_no": 3,
        "micro_skill_id": question["micro_skill_mappings"][0]["micro_skill_id"],
        "checkpoint_question_id": question["question_id"],
        "resume_policy": "SAME_QUESTION_AT_CHECKPOINT",
    }
    source["phase_payload"]["payload_type"] = "RESUME_SAME_INDEPENDENT_QUESTION"
    source["routing"].pop("return_question_id", None)
    source["routing"]["resume_question_id"] = question["question_id"]
    source["routing"]["resume_policy"] = "SAME_QUESTION_AT_CHECKPOINT"

    resumed = StudentModelSessionEventResponse.model_validate(source)
    projected = session_service._project_for_frontend(resumed)
    assert projected.phase_payload is not None
    assert projected.phase_payload.payload_type == "RESUME_SAME_INDEPENDENT_QUESTION"
    assert projected.routing.return_question_id == question["question_id"]
    assert resumed.journey_state.return_checkpoint is not None

    for reason_code in (
        "POST_PREREQUISITE_VERIFICATION_FAILED",
        "NO_PREREQUISITE_ROUTE_AVAILABLE",
        "EARLIEST_TOPIC_NO_BACKWARD_ROUTE",
    ):
        intervention_source = deepcopy(source)
        intervention_source["journey_state"]["intervention"] = {
            "intervention_id": f"INT-{reason_code}",
            "scope": "TOPIC",
            "topic_id": source["journey_state"]["topic_id"],
            "trigger_micro_skill_ids": [question["micro_skill_mappings"][0]["micro_skill_id"]],
            "reason_code": reason_code,
            "student_input_status": "REQUIRED",
        }
        intervention_source["phase_payload"] = {
            "phase": "PHASE_3_INDEPENDENT_PRACTICE",
            "payload_type": "INTERVENTION_INPUT_REQUIRED",
            "intervention_input_request": {
                "intervention_id": f"INT-{reason_code}",
            },
        }
        intervention_source["routing"]["reason_code"] = reason_code
        intervention_source["routing"]["next_action"] = "COLLECT_INTERVENTION_INPUT"
        intervention_source["status"]["intervention_required"] = True
        intervention = StudentModelSessionEventResponse.model_validate(intervention_source)
        request = session_service._project_for_frontend(intervention).phase_payload
        assert request is not None
        assert request.intervention_input_request is not None
        assert request.intervention_input_request.selection_options


def _popup(payload: dict[str, object] | None) -> dict[str, object] | None:
    """The §11 popup as it reaches the browser, or None if none is asked for."""

    return None if payload is None else payload.get("intervention_input_request")


def test_checkpoint_return_preserves_position_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    session = _start(monkeypatch, event)
    assert session.question_number == 3
    assert session.question_id is not None
    previous = event.journey_state.phase_3_independent_practice.model_copy(update={
        "used_question_ids": ["PREVIOUS-QUESTION", session.question_id],
        "completed_micro_skill_ids": ["COMPLETED-SKILL"],
        "verified_micro_skill_ids": ["COMPLETED-SKILL"],
    })
    returned = event.model_copy(update={"journey_state": event.journey_state.model_copy(update={
        "phase_3_independent_practice": previous.model_copy(update={"phase2_repair_count": 2}),
    })})
    session = session.model_copy(update={"student_model_event": returned, "current_phase": "GUIDED_PRACTICE"})
    updated = asyncio.run(session_service._apply_schema_event(session, returned))
    assert updated.question_number == 3
    assert updated.question_id == session.question_id
    assert updated.student_model_event is not None
    assert updated.student_model_event.journey_state.phase_3_independent_practice.used_question_ids == previous.used_question_ids


@pytest.mark.parametrize("damage", ["usage", "skill", "topic", "checkpoint", "history", "unrelated"])
def test_checkpoint_return_rejects_mismatches(monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    event = _event()
    session = _start(monkeypatch, event)
    phase3 = event.journey_state.phase_3_independent_practice
    assert phase3.return_checkpoint is not None
    phase3 = phase3.model_copy(update={"used_question_ids": [session.question_id, "OLD"]})
    event = event.model_copy(update={"journey_state": event.journey_state.model_copy(update={"phase_3_independent_practice": phase3})})
    session = session.model_copy(update={"student_model_event": event})
    bad = event.model_copy(deep=True)
    assert bad.phase_payload is not None and bad.phase_payload.question_set is not None
    question = bad.phase_payload.question_set.questions[0]
    if damage == "usage":
        question.question_usage_id = "CHANGED"
    elif damage == "skill":
        question.micro_skill_mappings = []
    elif damage == "topic":
        bad.journey_state.topic_id = "WRONG-TOPIC"
    elif damage == "checkpoint":
        bad.journey_state.phase_3_independent_practice.return_checkpoint = None
    elif damage == "history":
        bad.journey_state.phase_3_independent_practice.used_question_ids = []
    else:
        bad.phase_payload.question_set.questions.append(question.model_copy(update={"question_id": "OLD"}))
    with pytest.raises(HTTPException) as error:
        asyncio.run(session_service._apply_schema_event(session, bad))
    assert error.value.status_code == 503


def test_terminal_state_survives_silent_response_and_store_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _start(monkeypatch, _terminal(_event()))
    assert session.intervention is not None and session.intervention.feedback is None
    assert not session.allow_text_input and not session.allow_voice_input and not session.show_canvas
    restored = session_store._restore_session({"state": session.model_dump(mode="json")})
    assert restored.intervention == session.intervention

    # The case itself is internal; everything the browser routes on rides the
    # projected event.
    public = SessionResponse.model_validate(restored).model_dump(mode="json")
    assert "intervention" not in public and "pending_intervention_input" not in public
    event = public["student_model_event"]
    assert event["phase_payload"]["payload_type"] == "INTERVENTION_INPUT_REQUIRED"
    assert event["routing"]["next_action"] == "COLLECT_INTERVENTION_INPUT"
    assert event["status"]["intervention_required"] is True
    popup = _popup(event["phase_payload"])
    assert popup is not None and popup["intervention_id"] == "INT-001"
    assert popup["prompt"] == "What are you finding difficult?"
    assert [option["code"] for option in popup["selection_options"]] == [
        "DONT_UNDERSTAND_QUESTION", "DONT_KNOW_HOW_TO_START", "CANNOT_APPLY_IDEA",
        "WORDS_SYMBOLS_CONFUSING", "WORKING_MISTAKES", "OTHER",
    ]
    assert all(option["label"] for option in popup["selection_options"])

    # Phase 3 normally strips the event; a halted topic has no question to
    # protect, so the popup must survive that stripping.
    response = interaction_service._response_from(
        session_id=session.session_id, student_id=session.student_id, turn_id="T1",
        interaction_type="ANSWER_SUBMISSION", nudge_id=None, session=session,
        message="Paused", message_voice="", visual_cue=None, scaffold_steps=[],
        session_summary=None, conversation_action="WAIT_FOR_STUDENT", attempt_increment=0,
        status="processed", retry_safe=True,
    )
    assert response.student_model_event is not None
    assert response.student_model_event.phase_payload is not None
    assert response.student_model_event.phase_payload.payload_type == "INTERVENTION_INPUT_REQUIRED"

    # Ask 4: the same thing on GET /session, so a reload still asks.
    read = client.get(f"/session/{session.session_id}", params={"student_id": session.student_id})
    assert read.status_code == 200
    assert _popup(read.json()["student_model_event"]["phase_payload"]) is not None
    end = client.post("/session/end", json={"session_id": session.session_id, "student_id": session.student_id})
    assert end.status_code == 200
    assert _popup(end.json()["student_model_event"]["phase_payload"]) is not None


@pytest.mark.parametrize("path,body", [
    ("/interaction", {"input_source": "CHOICE", "interaction_type": "ANSWER_SUBMISSION", "selected_option_id": "A", "turn_id": "T1", "current_phase": "INDEPENDENT_PRACTICE", "concept_id": "ALG_LINEAR_ONE_STEP", "question_id": "Q1", "hint_count": 0}),
    ("/canvas/submit", {"snapshot_data_url": "data:image/png;base64,eA==", "turn_id": "T1"}),
    ("/session/{id}/orientation/start", {}),
    ("/session/{id}/orientation/complete", {"completed_video_ids": [], "completed_worked_example_ids": []}),
    ("/session/{id}/rescue/advance", {"question_id": "Q1", "rescue_id": "R1", "current_step_index": 1, "trigger": "UI_NEXT"}),
    ("/session/{id}/rescue/render-ack", {"action_id": "R1:step:1", "status": "RENDERED", "target_object_id": "OBJ1"}),
    ("/session/{id}/review/complete", {"turn_id": "T1"}),
])
def test_halt_blocks_learning_before_external_work(
    monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, object],
) -> None:
    session = _start(monkeypatch, _terminal(_event()))
    async def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("A halted learning request reached an external service")
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", forbidden)
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", forbidden)
    payload = {"student_id": session.student_id, **body}
    if "{id}" not in path:
        payload["session_id"] = session.session_id
    result = client.post(path.format(id=session.session_id), json=payload)
    assert result.status_code == 409, result.text
    assert "INTERVENTION_REQUIRED" in result.text


def test_only_explicit_resolution_clears_halt(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    with pytest.raises(HTTPException, match="omitted the unresolved intervention"):
        asyncio.run(session_service._apply_schema_event(session, _event()))
    assert session_service._sessions[session.session_id].intervention is not None
    assert terminal.journey_state.intervention is not None
    resolved = _event().model_copy(update={"journey_state": _event().journey_state.model_copy(update={
        "intervention": terminal.journey_state.intervention.model_copy(update={"state": "RESOLVED"}),
    })})
    updated = asyncio.run(session_service._apply_schema_event(session, resolved))
    assert updated.intervention is None and updated.allow_text_input


def test_wrong4_and_old_snapshots_keep_existing_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    event = event.model_copy(update={"status": event.status.model_copy(update={"intervention_required": True})})
    session = _start(monkeypatch, event)
    assert session.intervention is None
    stored = session.model_dump(mode="json")
    for key in ("intervention", "pending_intervention_input", "content_gap_detected"):
        stored.pop(key)
    stored["student_model_event"]["journey_state"].pop("intervention")
    for phase in ("phase_0_diagnostic", "phase_1_orientation", "phase_2_guided_learning", "phase_3_independent_practice", "review"):
        stored["student_model_event"]["journey_state"][phase].pop("return_checkpoint")
        stored["student_model_event"]["journey_state"][phase].pop("phase2_repair_count")
    restored = session_store._restore_session({"state": stored})
    assert restored.intervention is None and not restored.content_gap_detected


@pytest.mark.parametrize("changes,status", [
    ({"selected_reason_codes": []}, 422),
    ({"selected_reason_codes": ["INVALID"]}, 422),
    # The frontend's own fallback list is the accepted vocabulary.
    ({"selected_reason_codes": ["WORDS_SYMBOLS_CONFUSING", "WORKING_MISTAKES"]}, 200),
    ({"student_id": "ST999"}, 404),
    ({"intervention_id": "WRONG"}, 409),
    ({"topic_id": "WRONG"}, 409),
    ({"micro_skill_id": "WRONG"}, 409),
])
def test_feedback_validation(monkeypatch: pytest.MonkeyPatch, changes: dict[str, object], status: int) -> None:
    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        return _receipt(terminal, event)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    result = client.post("/interaction", json={**_request(session), **changes})
    assert result.status_code == status, result.text


def test_submission_is_the_one_thing_a_halted_student_may_send(monkeypatch: pytest.MonkeyPatch) -> None:
    """An answer is refused while paused; the §11 answer is not (ask 5)."""

    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        return _receipt(terminal, event)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    answer = client.post("/interaction", json={
        "session_id": session.session_id, "student_id": session.student_id,
        "interaction_type": "ANSWER_SUBMISSION", "input_source": "CHOICE",
        "selected_option_id": "A", "turn_id": "T-ANSWER",
        "current_phase": "INDEPENDENT_PRACTICE", "concept_id": session.concept_id,
        "question_id": "Q1", "hint_count": 0,
    })
    assert answer.status_code == 409 and "INTERVENTION_REQUIRED" in answer.text
    accepted = client.post("/interaction", json=_request(session))
    assert accepted.status_code == 200, accepted.text


def _receipt(event: StudentModelSessionEventResponse, request: InterventionInputSubmittedEvent) -> StudentModelSessionEventResponse:
    state = event.journey_state.intervention
    assert state is not None
    return event.model_copy(update={
        "request_id": request.request_id,
        "journey_state": event.journey_state.model_copy(update={
            "version": event.journey_state.version + 1,
            "intervention": state.model_copy(update={"feedback": request.feedback}),
        }),
    })


def test_feedback_http_receipt_reopen_and_conflicting_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    sent: list[InterventionInputSubmittedEvent] = []
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        assert access_token == "test-token"
        sent.append(event)
        return _receipt(terminal, event)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    body = _request(session)
    body["selected_reason_codes"] = ["DONT_KNOW_HOW_TO_START", "DONT_KNOW_HOW_TO_START"]
    assert TestClient(app).post("/interaction", json=body).status_code == 401
    submitted = client.post("/interaction", json=body)
    assert submitted.status_code == 200, submitted.text

    # TC-36: the popup closes onto the paused state, not back onto a question.
    event = submitted.json()["student_model_event"]
    assert event["routing"]["next_action"] == "AWAIT_INTERVENTION_REVIEW"
    assert event["status"]["intervention_required"] is True
    assert event["phase_payload"] is None
    assert submitted.json()["allow_text_input"] is False

    assert client.post("/interaction", json=body).status_code == 200
    assert len(sent) == 1 and sent[0].expected_journey_version == terminal.journey_state.version
    # Ask 6: a null audio_ref is accepted; the transcript is the evidence.
    assert sent[0].feedback.voice_input is not None
    assert sent[0].feedback.voice_input.audio_ref is None
    assert sent[0].feedback.voice_input.transcript == "I cannot choose the operation."
    assert sent[0].feedback.selected_reason_codes == ["DONT_KNOW_HOW_TO_START"]
    changed = {**body, "voice_input": {"provided": True, "audio_ref": None, "transcript": "Changed"}}
    assert client.post("/interaction", json={**changed, "turn_id": "INTERVENTION-2"}).status_code == 409
    reopened = _start(monkeypatch, _receipt(terminal, sent[0]))
    assert reopened.intervention is not None
    assert reopened.intervention.feedback == sent[0].feedback
    assert reopened.student_model_event is not None
    assert reopened.student_model_event.routing.next_action == "AWAIT_INTERVENTION_REVIEW"


def test_feedback_failure_restart_and_concurrency_keep_one_event(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    request = _request(session)
    feedback = InterventionFeedback(
        selected_reason_codes=["DONT_KNOW_HOW_TO_START"],
        voice_input=InterventionVoiceInput(provided=True, transcript="I cannot choose the operation."),
    )
    sent: list[InterventionInputSubmittedEvent] = []
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        sent.append(event)
        if len(sent) == 1:
            raise HTTPException(status_code=503, detail="Upstream unavailable")
        await asyncio.sleep(0)
        return _receipt(terminal, event)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    async def submit() -> object:
        # The route holds this lock; the direct caller must too.
        async with session_service.interaction_lock_for(session.session_id):
            return await session_service.submit_intervention_input(
                session.session_id, session.student_id, request["intervention_id"], feedback,
                "test-token", topic_id=request["topic_id"], micro_skill_id=request["micro_skill_id"],
            )
    async def exercise() -> None:
        with pytest.raises(HTTPException):
            await submit()
        pending = session_service._sessions[session.session_id]
        assert pending.intervention is not None and pending.intervention.feedback is None
        session_service._sessions[session.session_id] = session_store._restore_session({"state": pending.model_dump(mode="json")})
        results = await asyncio.gather(*[submit() for _ in range(2)])
        assert all(result.intervention is not None and result.intervention.feedback is not None for result in results)
    asyncio.run(exercise())
    assert len(sent) == 2 and sent[0] == sent[1]


def test_terminal_answer_stops_followup_and_keeps_controls_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    initial = _event()
    session = _start(monkeypatch, initial)
    question = session.active_student_model_question
    assert question is not None and question.student_view.options
    sent: list[str] = []
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        sent.append(event.event_type)
        assert len(sent) == 1, "Terminal response triggered another Student Model call"
        return _terminal(initial).model_copy(update={"request_id": event.request_id})
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    answered = client.post("/interaction", json={
        "session_id": session.session_id, "student_id": session.student_id,
        "interaction_type": "ANSWER_SUBMISSION", "input_source": "CHOICE",
        "selected_option_id": question.student_view.options[0].option_id,
        "turn_id": "TERMINAL-CHOICE", "current_phase": "INDEPENDENT_PRACTICE",
        "concept_id": session.concept_id, "question_id": question.question_id, "hint_count": 0,
    })
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert _popup(body["student_model_event"]["phase_payload"]) is not None
    assert body["student_model_event"]["routing"]["next_action"] == "COLLECT_INTERVENTION_INPUT"
    assert not body["show_canvas"] and not body["allow_text_input"] and not body["allow_voice_input"]
    assert len(sent) == 1


def test_content_gap_visible_in_session_and_silent_response(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    event = event.model_copy(update={"routing": event.routing.model_copy(update={"content_gap_detected": True})})
    session = _start(monkeypatch, event)
    response = interaction_service._response_from(
        session_id=session.session_id, student_id=session.student_id, turn_id="GAP1",
        interaction_type="ANSWER_SUBMISSION", nudge_id=None, session=session,
        message="Content unavailable", message_voice="", visual_cue=None, scaffold_steps=[],
        session_summary=None, conversation_action="WAIT_FOR_STUDENT", attempt_increment=0,
        status="processed", retry_safe=True,
    )
    assert response.content_gap_detected and session.intervention is None
    assert SessionResponse.model_validate(session).content_gap_detected
    assert response.current_phase == "INDEPENDENT_PRACTICE"


@pytest.mark.parametrize("damage", ["resolution", "phase", "checkpoint", "receipt"])
def test_feedback_acknowledgement_cannot_change_learning(monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    terminal = _terminal(_event())
    session = _start(monkeypatch, terminal)
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        response = _receipt(terminal, event).model_copy(deep=True)
        assert response.journey_state.intervention is not None
        if damage == "resolution":
            response.journey_state.intervention.state = "RESOLVED"
        elif damage == "phase":
            response.journey_state.current_phase = "REVIEW"
        elif damage == "checkpoint":
            response.journey_state.phase_3_independent_practice.return_checkpoint = None
        else:
            response.journey_state.intervention.feedback = None
        return response
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    result = client.post("/interaction", json=_request(session))
    assert result.status_code == 503, result.text
    stored = session_service._sessions[session.session_id]
    assert stored.intervention is not None and stored.intervention.feedback is None
    assert stored.pending_intervention_input is not None


def test_feedback_request_identity_survives_new_session(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal = _terminal(_event())
    first = _start(monkeypatch, terminal)
    second = _start(monkeypatch, terminal)
    sent: list[InterventionInputSubmittedEvent] = []
    async def send(adapter: StudentModelServiceAdapter, event: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        assert isinstance(event, InterventionInputSubmittedEvent)
        sent.append(event)
        # Simulate the upstream receipt keyed by stable request identity.
        return _receipt(terminal, sent[0])
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    assert client.post("/interaction", json=_request(first)).status_code == 200
    conflict = {
        **_request(second),
        "voice_input": {"provided": True, "audio_ref": None, "transcript": "Changed"},
    }
    assert client.post("/interaction", json=conflict).status_code == 409
    assert len(sent) == 2 and sent[0].request_id == sent[1].request_id
    assert first.session_id not in sent[0].request_id


def test_checkpoint_new_attempt_and_duplicate_are_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    session = _start(monkeypatch, event)
    question = session.active_student_model_question
    assert question is not None and question.student_view.options
    sent: list[str] = []
    async def send(adapter: StudentModelServiceAdapter, request: StudentModelSessionEvent, access_token: str) -> StudentModelSessionEventResponse:
        sent.append(request.request_id)
        return event.model_copy(update={"request_id": request.request_id})
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send)
    body = {
        "session_id": session.session_id, "student_id": session.student_id,
        "interaction_type": "ANSWER_SUBMISSION", "input_source": "CHOICE",
        "selected_option_id": question.student_view.options[0].option_id,
        "turn_id": "CHECKPOINT-1", "current_phase": "INDEPENDENT_PRACTICE",
        "concept_id": session.concept_id, "question_id": question.question_id, "hint_count": 0,
    }
    first = client.post("/interaction", json=body)
    assert first.status_code == 200, first.text
    first_count = len(sent)
    replay = client.post("/interaction", json=body)
    assert replay.status_code == 200 and replay.json()["status"] == "DUPLICATE_TURN"
    assert len(sent) == first_count
    returned = session_service._sessions[session.session_id]
    assert returned.student_model_event is not None
    repair_session = returned.model_copy(update={"current_phase": "GUIDED_PRACTICE"})
    asyncio.run(session_service._apply_schema_event(repair_session, returned.student_model_event))
    second = client.post("/interaction", json={**body, "turn_id": "CHECKPOINT-2"})
    assert second.status_code == 200, second.text
    assert len(sent) > first_count
    assert second.json()["question_id"] == question.question_id
    assert session_service._sessions[session.session_id].question_number == 3


def test_null_payload_content_gap_can_reopen(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    event = event.model_copy(update={
        "phase_payload": None,
        "routing": event.routing.model_copy(update={"content_gap_detected": True}),
    })
    session = _start(monkeypatch, event)
    assert session.content_gap_detected and session.intervention is None
    assert session.question_id is None and session.current_phase == "INDEPENDENT_PRACTICE"


def test_terminal_marker_requires_case_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _start(monkeypatch, _event())
    terminal = _terminal(_event())
    terminal = terminal.model_copy(update={"journey_state": terminal.journey_state.model_copy(update={"intervention": None})})
    with pytest.raises(HTTPException) as error:
        asyncio.run(session_service._apply_schema_event(session, terminal))
    assert error.value.status_code == 503


def test_reopen_uses_checkpoint_answer_spec_not_first_array_item(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _event()
    assert event.phase_payload is not None and event.phase_payload.question_set is not None
    checkpoint_question = event.phase_payload.question_set.questions[0]
    event.phase_payload.question_set.questions.insert(
        0, checkpoint_question.model_copy(update={"question_id": "ANOTHER-QUESTION", "question_usage_id": "ANOTHER-USAGE"})
    )
    session = _start(monkeypatch, event)
    assert session.active_student_model_question == checkpoint_question
    assert session.question_id == checkpoint_question.question_id
    assert session.question_number == 3
