import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.session import QuestionAttemptRecord, SessionEndRequest, SessionRecord
from app.services import session_service

client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def test_generated_session_ids_are_unique_and_valid() -> None:
    session_ids = [session_service._build_session_id() for _ in range(1001)]

    assert len(set(session_ids)) == 1001
    assert all(session_id.startswith("SESSION") for session_id in session_ids)
    for session_id in session_ids:
        SessionEndRequest(session_id=session_id, student_id="ST001")


def seed_graded_attempt(session_id: str) -> None:
    """/session/end refuses sessions with no graded attempts; seed one."""

    session = session_service._sessions[session_id]
    session_service._sessions[session_id] = session.model_copy(
        update={
            "per_question_history": [
                QuestionAttemptRecord(
                    question_id="ALG_EQ_GP_001",
                    question_text="Solve for x: x + 6 = 10",
                    phase="GUIDED_PRACTICE",
                    evaluation="CORRECT",
                    input_source="TEXT",
                    hint_level_used=0,
                    attempted_at=datetime.now(timezone.utc),
                )
            ]
        }
    )


def test_session_start_rejects_invalid_interaction_mode() -> None:
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TELEPATHY",
        },
    )

    assert response.status_code == 422
    assert response.json()["field"] == "interaction_mode"


def test_review_session_with_no_attempts_can_end() -> None:
    session_id = "SESSION001"
    session_service._sessions[session_id] = SessionRecord.model_construct(
        session_id=session_id,
        student_id="ST001",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase="REVIEW",
        current_question=None,
        question_number=1,
        interaction_mode="TEXT",
        ui_state="REVIEW",
        message="Session Review — practice questions complete.",
        hint_count=0,
        last_tutor_response_at=datetime.now(timezone.utc),
        status="started",
        student_model_event=object(),
    )
    try:
        ended = asyncio.run(
            session_service.end_session(
                SessionEndRequest(session_id=session_id, student_id="ST001")
            )
        )
        assert ended.status == "ended"
        assert ended.session_summary is not None
        assert ended.session_summary.session_performance.total_attempts == 0
    finally:
        session_service._sessions.pop(session_id, None)


def _worked_session_with_no_recorded_history(session_id: str) -> SessionRecord:
    """A resumed guided session: Student Model's attempt counter, no local history.

    `attempt_count` is restored from the journey payload's
    `current_attempt_sequence`; `per_question_history` has no source in that
    payload and so comes back empty. Live SESSION04b34eb30d494bd186c9b96d05586de1
    showed attempt_count 7 against an empty history (Manav, 26 Aug).
    """

    return SessionRecord.model_construct(
        session_id=session_id,
        student_id="ST015",
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        current_phase="GUIDED_PRACTICE",
        current_question="Which is the general rule:",
        question_number=1,
        interaction_mode="TEXT",
        ui_state="GUIDED_PRACTICE",
        message="Keep going.",
        hint_count=2,
        attempt_count=7,
        per_question_history=[],
        canvas_submissions=[],
        hint_levels_used=[1, 2],
        phase_transitions=[],
        conversation_history=[],
        recommended_entry_phase=None,
        last_tutor_response_at=datetime.now(timezone.utc),
        status="started",
        student_model_event=object(),
    )


def test_worked_session_with_no_recorded_history_still_ends() -> None:
    """Row 17's 'un-endable session' does not reproduce on this build.

    The precondition Manav observed is real; the consequence is not. Pinned so
    the claim is not re-raised from the state alone.
    """

    session_id = "SESSION015"
    session_service._sessions[session_id] = _worked_session_with_no_recorded_history(
        session_id
    )
    try:
        ended = asyncio.run(
            session_service.end_session(
                SessionEndRequest(session_id=session_id, student_id="ST015")
            )
        )
        assert ended.status == "ended"
        assert ended.session_summary is not None
    finally:
        session_service._sessions.pop(session_id, None)


def test_attempt_count_and_summary_total_attempts_measure_different_things() -> None:
    """The two counters are not inconsistent; they have different scopes.

    `attempt_count` is seeded per session from the Student Model journey's
    `current_attempt_sequence` (`start_session`), so it carries prior work on
    the current question into a resumed session. `total_attempts` counts what
    THIS session graded, via `per_question_history`. A resumed session that
    has not yet graded an answer therefore reads 7 and 0 at the same time, and
    both are correct.

    Pinned so the pairing is not re-filed as data loss (Manav, 26 Aug, row 17).
    """

    session = _worked_session_with_no_recorded_history("SESSION016")

    summary = session_service.assemble_session_summary(
        session,
        datetime.now(timezone.utc),
    )

    assert session.attempt_count == 7
    assert summary.session_performance.total_attempts == 0
    assert summary.per_question_history == []


def test_get_session_rejects_malformed_session_id() -> None:
    response = client.get("/session/bad", params={"student_id": "ST001"})

    assert response.status_code == 422
    assert response.json()["field"] == "session_id"


def test_get_session_returns_404_for_unknown_valid_session_id() -> None:
    response = client.get("/session/SESSION777", params={"student_id": "ST001"})

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "HTTP_ERROR"
    assert body["message"] == "Session with ID SESSION777 was not found."
