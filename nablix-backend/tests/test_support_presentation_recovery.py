"""Student Model accepted the rung; building its presentation failed.

The live trace behind this: a Parallel Example reached Student Model, which
recorded the escalation and advanced the journey — and the Tutor Backend then
crashed assembling the steps. The turn failed AFTER the write, so the session
was one rung behind an upstream journey it could no longer match, and the next
learner turn decided a FRESH escalation against the advanced version. That is
what produced the journey conflict, the recovery banner, and the reset teaching
evidence the student saw.

The contract these tests hold:

  1. The escalation is persisted before it is sent, so the exact event is
     recoverable whatever happens next.
  2. A presentation failure blocks further learner turns rather than deciding a
     second escalation.
  3. GET /session replays the SAME request_id. Student Model answers an
     already-processed request with its original envelope, so recovery rebuilds
     the rung from the response the failed turn received.
  4. Nothing about the question the student is on moves: identity, counters and
     teaching evidence are exactly as they were.
"""

import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.main import app
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from app.services.rescue_presentation import active_rescue_from
from tests.test_session_events import _event_response, _session_opened_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})

WRONG_ANSWER = "x = 4"


@pytest.fixture
def sent_events(monkeypatch: pytest.MonkeyPatch) -> list[StudentModelSessionEvent]:
    """A Student Model that serves a Parallel Example on the wrong-4 escalation.

    Shortened deliberately: the rung the presentation fails on is the subject
    here, not the ladder that leads to it (test_session_events walks that).
    """

    events: list[StudentModelSessionEvent] = []
    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
        student_model_atomic_guided_events_enabled=True,
    )

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        events.append(event)
        if event.event_type == "SESSION_OPENED":
            body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        elif event.event_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED":
            body = _event_response("MAXIMUM_GUIDED_SUPPORT_PARALLEL", event.request_id)
        else:
            body = _event_response(event.event_type, event.request_id)
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(interaction_service, "get_settings", lambda: settings)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    return events


def _start(student_id: str) -> str:
    started = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert started.status_code == 200, started.text
    return started.json()["session_id"]


def _answer(session_id: str, student_id: str, turn: str) -> object:
    return client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": student_id,
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": turn,
            "text_input": WRONG_ANSWER,
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "Q-T02-004",
            "hint_count": 0,
        },
    )


def _break_presentation_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the FIRST rung assembly, exactly as the 80-character cap did."""

    calls: list[int] = []

    def flaky(question_id: str, rescue: object, request_id: str) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise HTTPException(status_code=409, detail="Rescue content is empty.")
        return active_rescue_from(question_id, rescue, request_id)  # type: ignore[arg-type]

    monkeypatch.setattr(interaction_service, "active_rescue_from", flaky)


def test_a_failed_presentation_is_recovered_by_replaying_the_same_event(
    sent_events: list[StudentModelSessionEvent],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _start("ST771")
    for turn in range(1, 4):
        assert _answer(session_id, "ST771", f"TURN-W{turn}").status_code == 200

    before = session_service._sessions[session_id]
    _break_presentation_once(monkeypatch)

    failed = _answer(session_id, "ST771", "TURN-W4")
    assert failed.status_code != 200

    # 1. The escalation Student Model accepted is held, not re-decided.
    pending = session_service._sessions[session_id].pending_support_event
    assert pending is not None
    assert pending.event_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
    escalation_request_id = pending.request_id
    assert sent_events[-1].request_id == escalation_request_id

    # 2. No further learner turn is accepted, and none reaches Student Model.
    events_after_failure = len(sent_events)
    blocked = _answer(session_id, "ST771", "TURN-W5")
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error_code"] == "SESSION_STATE_REFRESH_REQUIRED"
    assert len(sent_events) == events_after_failure, (
        "a refusal still decided a fresh escalation against the advanced journey"
    )

    # 3. The recovering read replays the identical request id.
    recovered = client.get(
        f"/session/{session_id}", params={"student_id": "ST771"},
    )
    assert recovered.status_code == 200, recovered.text
    assert sent_events[-1].request_id == escalation_request_id
    assert session_service._sessions[session_id].pending_support_event is None

    # 4. The student is still on the question they were on, with their work.
    after = session_service._sessions[session_id]
    assert after.question_id == before.question_id
    assert after.current_question == before.current_question
    assert after.wrong_attempt_count >= before.wrong_attempt_count
    assert after.guided_teaching_state == before.guided_teaching_state
    assert after.active_guided_rescue is not None
    assert after.active_guided_rescue.rescue_type == "PARALLEL_EXAMPLE"
    assert recovered.json()["question_id"] == before.question_id


def test_a_restore_keeps_the_rung_student_model_re_serves(
    sent_events: list[StudentModelSessionEvent],
) -> None:
    """SESSION_OPENED now answers with the rung, and the restore must keep it.

    Student Model re-serves a Parallel Example as a RESCUE payload carrying the
    question. Applying only the journey and the question handed the student
    their question back with the walkthrough silently dropped -- the same rung
    loss this change exists to end, one layer further out.
    """

    import copy

    session_id = _start("ST772")
    session = session_service._sessions[session_id]
    stored = session.student_model_event
    assert stored is not None

    body = copy.deepcopy(_session_opened_response("PHASE_2_GUIDED_LEARNING"))
    rescue = _event_response("MAXIMUM_GUIDED_SUPPORT_PARALLEL", "REQ-RESTORE")
    assert isinstance(body["phase_payload"], dict)
    body["phase_payload"]["payload_type"] = "RESCUE"
    body["phase_payload"]["rescue_to_serve"] = rescue["phase_payload"]["rescue_to_serve"]
    body["phase_payload"]["support_to_serve"] = None
    body["request_id"] = f"{session_id}:RECOVER-1"
    response = StudentModelSessionEventResponse.model_validate(body)

    class _Restoring:
        async def send_session_event(self, event: object, token: str) -> object:
            del event, token
            return response

    recovering = session.model_copy(update={"journey_recovery_required": True})
    session_service._sessions[session_id] = recovering
    restored = asyncio.run(interaction_service._initialize_restored_schema_phase(
        recovering, _Restoring(), "tok", for_read=True))

    assert restored.active_guided_rescue is not None
    assert restored.active_guided_rescue.rescue_type == "PARALLEL_EXAMPLE"
    assert restored.active_guided_rescue.question_id == restored.question_id
