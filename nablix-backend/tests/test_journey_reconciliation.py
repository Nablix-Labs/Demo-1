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
    """Reproduces the production failure, then proves the refresh actually recovers.

    Live shape: session cached v8 with Q-T01-009 active; the Student Model was
    already at v11 with current_question_id null and Q-T01-009 in used ids. The
    first submission 409s.

    An immediate re-POST is now refused too, and that is the fix rather than a
    regression. Observed at 14:49:35 UTC: recovery restored a question, and the
    submission already in flight — carrying ink drawn for Q-T01-005 — was graded
    against it. Work drawn for one question must not become an answer to
    another, so the client refreshes first (GET /session, which performs the
    recovery) and only then submits against the question it was actually given.
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

    # No grading until the client has the restored question. Re-POSTing the same
    # body would submit Q-T01-005's work against whatever recovery selects.
    blocked = client.post("/interaction", json=payload)
    assert blocked.status_code == 409, blocked.json()
    assert blocked.json()["error_code"] == "SESSION_STATE_REFRESH_REQUIRED"
    assert len(sent) == 1, "a refusal still asked Student Model for something"

    # The refresh is what recovers, and it recovers to the effective phase:
    # current_phase was Phase 3, recommended_entry_phase Phase 2, and Student
    # Model's own session_open honours the recommendation.
    refreshed = client.get(
        f"/session/{session_id}", params={"student_id": "ST025"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert all(version != stale_version for _, version, _ in sent[1:])
    assert sent[1][0] in {
        "SESSION_OPENED",
        "GUIDED_QUESTION_SET_REQUESTED",
        "INDEPENDENT_QUESTION_SET_REQUESTED",
    }
    restored = refreshed.json()
    assert restored["question_id"] is not None
    assert restored["question_id"] != body["question_id"], (
        "recovery handed back the stale question"
    )

    # Now the client can answer -- against the question it was just given.
    recovered = client.post(
        "/interaction",
        json={**payload, "turn_id": "TURN-ST025-2", "question_id": restored["question_id"],
              "current_phase": restored["current_phase"]},
    )
    assert recovered.status_code == 200, recovered.json()


def test_reconcile_resumes_at_the_effective_phase() -> None:
    """The ST010 conflict shape: current Phase 3, recommended Phase 2.

    Verified at 14:49:28 UTC. Selecting current_phase here restarted the
    independent set while an outstanding Phase 2 repair was recommended, so the
    student was handed a brand-new question instead of the repair they owed.
    """

    body = _start_session("ST030")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    fresh_journey = session.student_model_event.journey_state.model_dump(mode="json")
    fresh_journey["version"] = stale_version + 3
    fresh_journey["student_id"] = "ST030"
    fresh_journey["current_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
    fresh_journey["recommended_entry_phase"] = "PHASE_2_GUIDED_LEARNING"
    fresh_journey["phase_2_guided_learning"] = {
        "status": "NOT_STARTED",
        "phase_visit_no": None,
        "target_micro_skill_ids": ["T01.M5"],
    }
    conflict = JourneyVersionConflict({"current_journey_state": fresh_journey})

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST030", conflict)
    )

    recovered = session_service._sessions[session_id]
    assert recovered.current_phase == "GUIDED_PRACTICE"
    assert recovered.ui_state == "GUIDED_PRACTICE"
    assert recovered.recommended_entry_phase == "GUIDED_PRACTICE"
    # Nothing from the stale version survives, and no work may be submitted
    # until the client has refreshed.
    assert recovered.journey_recovery_required is True
    assert recovered.question_id is None
    assert recovered.show_canvas is False


def test_reconcile_keeps_an_absent_recommendation_absent() -> None:
    """A null recommendation means "this topic cannot be resumed as learning".

    Student Model sets it deliberately for a topic in prerequisite lookup or
    paused for intervention. Folding current_phase into the field advertised a
    recommendation it had withheld, and disagreed with _apply_schema_event, which
    keeps the null for the same input.
    """

    body = _start_session("ST031")
    session_id = body["session_id"]
    session = session_service._sessions[session_id]
    stale_version = session.student_model_event.journey_state.version

    fresh_journey = session.student_model_event.journey_state.model_dump(mode="json")
    fresh_journey["version"] = stale_version + 3
    fresh_journey["student_id"] = "ST031"
    fresh_journey["current_phase"] = "PHASE_3_INDEPENDENT_PRACTICE"
    fresh_journey["recommended_entry_phase"] = None
    conflict = JourneyVersionConflict({"current_journey_state": fresh_journey})

    asyncio.run(
        session_service.reconcile_journey_conflict(session_id, "ST031", conflict)
    )

    recovered = session_service._sessions[session_id]
    assert recovered.recommended_entry_phase is None
    # The student still resumes somewhere: absent a recommendation, that is the
    # current phase.
    assert recovered.current_phase == "INDEPENDENT_PRACTICE"
