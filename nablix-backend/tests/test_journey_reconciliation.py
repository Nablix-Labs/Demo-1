"""Regression coverage for the two-session journey-version staleness bug.

Root cause: a Tutor Backend session caches the Student Model's journey state
after each call (interaction_service.py send_session_event sites). If another
session for the same student/topic advances the real journey, this session's
cache never learns about it — it keeps resending the stale
expected_journey_version and looping on 409 JOURNEY_VERSION_CONFLICT forever,
because GET /session/{id} only ever returns the locally stored record.

session_service.reconcile_journey_conflict() closes that gap: on a 409, it
reads the Student Model's own current_journey_state out of the conflict and
patches the session's cache with it, so the next retry uses the real version.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.core.config import Settings
from app.core.exceptions import JourneyVersionConflict
from app.main import app
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import session_service
from tests.test_session_events import _event_response, _session_opened_response

client = TestClient(app, headers={"Authorization": "Bearer test-token"})


@pytest.fixture(autouse=True)
def schema_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same shape as test_canvas.py's fixture: a working default SESSION_OPENED
    response, so _start_session succeeds; individual tests layer their own
    send_session_event on top for the call under test."""

    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
        qdrant_url="https://qdrant.test",
        qdrant_api_key="test-key",
    )

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = (
            _session_opened_response("PHASE_2_GUIDED_LEARNING")
            if event.event_type == "SESSION_OPENED"
            else _event_response(event.event_type, event.request_id)
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)


def _start_session(student_id: str) -> dict[str, object]:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_reconcile_handles_the_200_with_conflict_status_shape() -> None:
    """JourneyVersionConflict has two raise sites with two different shapes:
    the true-409 path passes {"current_journey_state": ...}, but a 200 whose
    body has status.status_code == JOURNEY_VERSION_CONFLICT passes the full
    response dict, where the same data sits under "journey_state" instead —
    see student_model.py's two `raise JourneyVersionConflict(...)` sites.
    """

    body = _start_session("ST024")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    fresh_journey = session.student_model_event.journey_state.model_dump(mode="json")
    fresh_journey["version"] = stale_version + 1
    fresh_journey["student_id"] = "ST024"
    conflict = JourneyVersionConflict(
        {
            "schema_version": "3.0",
            "request_id": "REQ-1",
            "processed_at": "2026-08-12T00:00:00Z",
            "journey_state": fresh_journey,
        }
    )

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST024", conflict)
    )

    updated = session_service._sessions[session_id].student_model_event.journey_state
    assert updated.version == stale_version + 1


def test_reconcile_updates_the_stale_session_from_a_409_body() -> None:
    body = _start_session("ST020")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    fresh_journey = session.student_model_event.journey_state.model_dump(mode="json")
    fresh_journey["version"] = stale_version + 3
    fresh_journey["student_id"] = "ST020"
    conflict = JourneyVersionConflict({"current_journey_state": fresh_journey})

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST020", conflict)
    )

    recovered = session_service._sessions[session_id]
    assert recovered.student_model_event.journey_state.version == stale_version + 3
    assert recovered.question_id is None
    assert recovered.active_student_model_question is None


def test_reconcile_ignores_a_conflict_for_a_different_student() -> None:
    body = _start_session("ST021")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    fresh_journey = session.student_model_event.journey_state.model_dump(mode="json")
    fresh_journey["version"] = stale_version + 3
    fresh_journey["student_id"] = "ST099"
    conflict = JourneyVersionConflict({"current_journey_state": fresh_journey})

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST021", conflict)
    )

    unchanged = session_service._sessions[session_id].student_model_event.journey_state
    assert unchanged.version == stale_version


def test_reconcile_ignores_a_conflict_with_no_usable_state() -> None:
    body = _start_session("ST022")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    conflict = JourneyVersionConflict(
        {"error_code": "JOURNEY_VERSION_CONFLICT", "message": "no state included"}
    )

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST022", conflict)
    )

    unchanged = session_service._sessions[session_id].student_model_event.journey_state
    assert unchanged.version == stale_version


def test_interaction_409_reconciles_the_session_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real seam: /interaction still 409s to the client, but by the time the
    request finishes the session holds the authoritative version AND has dropped
    the question state derived from the stale one.

    The client retries with the SAME turn_id: the rejected attempt raised before
    reaching _cache_response, so it recorded no attempt and no Student Model
    event, and reusing the id preserves exactly-once semantics rather than
    booking a second submission.
    """

    body = _start_session("ST023")
    session_id = body["session_id"]
    stale_version = (
        session_service._sessions[session_id].student_model_event.journey_state.version
    )

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        fresh = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        journey = fresh["journey_state"]
        assert isinstance(journey, dict)
        journey["student_id"] = "ST023"
        journey["topic_id"] = event.topic_id
        journey["version"] = stale_version + 3
        raise JourneyVersionConflict({"current_journey_state": journey})

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)

    response = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST023",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "text_input": "x = 4",
            "turn_id": "TURN-ST023-1",
            "current_phase": body["current_phase"],
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": body["question_id"],
            "hint_count": 0,
        },
    )

    assert response.status_code == 409, response.json()
    assert response.json()["error_code"] == "JOURNEY_VERSION_CONFLICT"

    recovered = session_service._sessions[session_id]
    assert recovered.student_model_event.journey_state.version == stale_version + 3
    # The v8-derived question must not survive onto the v11 journey.
    assert recovered.question_id is None
    assert recovered.current_question is None
    assert recovered.correct_answer is None
    assert recovered.active_student_model_question is None


def test_live_shape_retry_recovers_with_a_fresh_authoritative_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reproduces the production failure, then proves the retry actually recovers.

    Live shape: session cached v8 with Q-T01-009 active; the Student Model was
    already at v11 with current_question_id null and Q-T01-009 in used ids. The
    first submission 409s. The retry (same turn_id) must not resend Q-T01-009 —
    _initialize_restored_schema_phase should re-derive the question from the
    authoritative envelope first.
    """

    body = _start_session("ST025")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    authoritative = session.student_model_event.journey_state.model_dump(mode="json")
    authoritative["version"] = stale_version + 3
    authoritative["student_id"] = "ST025"

    sent: list[tuple[str, int, str | None]] = []
    conflicted = False

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        nonlocal conflicted
        sent.append(
            (
                event.event_type,
                getattr(event, "expected_journey_version", -1),
                getattr(event, "question_id", None),
            )
        )
        if not conflicted:
            conflicted = True
            raise JourneyVersionConflict({"current_journey_state": authoritative})
        # The restore path asks for a question set; everything else is the attempt.
        fresh = (
            _session_opened_response("PHASE_2_GUIDED_LEARNING")
            if event.event_type.endswith("QUESTION_SET_REQUESTED")
            else _event_response(event.event_type, event.request_id)
        )
        journey = fresh["journey_state"]
        assert isinstance(journey, dict)
        journey["student_id"] = "ST025"
        journey["version"] = stale_version + 4
        fresh["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(fresh)

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)

    payload = {
        "session_id": session_id,
        "student_id": "ST025",
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "TEXT",
        "text_input": "m-4",
        "turn_id": "TURN-ST025-1",
        "current_phase": body["current_phase"],
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": body["question_id"],
        "hint_count": 0,
    }

    first = client.post("/interaction", json=payload)
    assert first.status_code == 409
    assert sent[0][1] == stale_version

    # Same turn_id: the rejected attempt booked nothing, so this is a retry of
    # the same submission, not a second one.
    second = client.post("/interaction", json=payload)

    assert second.status_code == 200, second.json()
    # The retry carried the authoritative version, never the stale one again.
    assert all(version != stale_version for _, version, _ in sent[1:])
    # It re-derived the question instead of resending the v8 one.
    assert sent[1][0] in {
        "GUIDED_QUESTION_SET_REQUESTED",
        "INDEPENDENT_QUESTION_SET_REQUESTED",
    }
