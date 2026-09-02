"""How many times the student answered Phase 3 on their own.

The session receipt has no way to say this today. `total_attempts` counts every
phase together, so a student who answered twice in Independent Practice and
eleven times in Guided Practice reads as thirteen, and the frontend cannot tell
the two apart without re-deriving the rule from `per_question_history` -- which
would be a client-side copy of a decision that belongs here.

The count is of *terminal* Phase 3 results only: the student either answered
independently (`INDEPENDENTLY_VERIFIED`) or needs the rescue
(`RESCUE_REQUIRED`). Unreadable work, a turn still awaiting a submission, a
hint, a voice attachment, a stale turn and a duplicate retry are all not
attempts, and each of them has stranded a counter somewhere before.
"""

import pytest
from fastapi.testclient import TestClient

from app.adapters.student_model import StudentModelServiceAdapter
from app.main import app
from app.models.adapters import (
    AdapterContext,
    RAGResult,
    StudentModelResult,
    TutorResult,
)
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from app.services import interaction_service, session_service
from tests.test_session_events import _session_opened_response


client = TestClient(app, headers={"Authorization": "Bearer test-token"})
SNAPSHOT = "data:image/png;base64,aGVsbG8="


def _phase3_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every event answers with a live Phase 3 journey."""

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        StudentModelServiceAdapter, "send_session_event", send_session_event
    )


def _tutor(outcome: str | None, *, terminal: bool, evaluation: str) -> TutorResult:
    return TutorResult(
        evaluation=evaluation,
        error_type="NONE" if evaluation == "CORRECT" else "CONCEPTUAL",
        intent="SUBMITTING_ANSWER",
        response_strategy="CONFIRM_CORRECT" if evaluation == "CORRECT" else "CLARIFY",
        tutor_message="Recorded.",
        tutor_message_voice="Recorded.",
        voice_optimised=True,
        hint_level=0,
        answer_reveal_allowed=False,
        confidence=0.95,
        input_source="CANVAS",
        attempt_increment=1 if terminal else 0,
        recommended_conversation_action=(
            "ADVANCE_TO_NEXT_QUESTION" if terminal else "WAIT_FOR_STUDENT"
        ),
        question_completed=terminal,
        answer_value_confirmed=outcome == "INDEPENDENTLY_VERIFIED",
        reasoning_complete=terminal,
        independent_outcome=outcome,
        independent_success=(outcome == "INDEPENDENTLY_VERIFIED") if terminal else None,
        independent_attempt_terminal=terminal,
    )


def _pipeline_returning(tutor: TutorResult, monkeypatch: pytest.MonkeyPatch) -> None:
    async def pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        student = StudentModelResult(
            mastery_status="DEVELOPING",
            continuity_status="on_track",
            recommended_entry_phase="INDEPENDENT_PRACTICE",
            hint_dependency_score=0.0,
            intervention_required=False,
        )
        return RAGResult(documents=[], retrieval_confidence=0.0), student, tutor

    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", pipeline)


def _start(student_id: str) -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def _submit(session_id: str, student_id: str, turn_id: str, **overrides: object):
    return client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": student_id,
            "turn_id": turn_id,
            "snapshot_data_url": SNAPSHOT,
            **overrides,
        },
    )


def _count(session_id: str, student_id: str) -> int:
    return session_service._get_owned_session(
        session_id, student_id
    ).independent_attempt_count


def test_a_verified_independent_answer_counts_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("INDEPENDENTLY_VERIFIED", terminal=True, evaluation="CORRECT"),
        monkeypatch,
    )
    session_id = _start("ST401")

    assert _submit(session_id, "ST401", "TURN-401-1").status_code == 200
    assert _count(session_id, "ST401") == 1


def test_a_retry_of_the_same_turn_does_not_count_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The duplicate is served from cache, so it must not touch the counter."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("INDEPENDENTLY_VERIFIED", terminal=True, evaluation="CORRECT"),
        monkeypatch,
    )
    session_id = _start("ST402")

    _submit(session_id, "ST402", "TURN-402-1")
    duplicate = _submit(session_id, "ST402", "TURN-402-1")

    assert duplicate.json()["status"] == "DUPLICATE_TURN"
    assert _count(session_id, "ST402") == 1


def test_a_rescue_required_answer_is_still_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The student answered on their own and got it wrong. That is an attempt."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("RESCUE_REQUIRED", terminal=True, evaluation="INCORRECT"),
        monkeypatch,
    )
    session_id = _start("ST403")

    _submit(session_id, "ST403", "TURN-403-1")

    assert _count(session_id, "ST403") == 1


def test_unreadable_work_is_not_an_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """INPUT_UNCLEAR asks the student to rewrite. Nothing was answered yet."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("INPUT_UNCLEAR", terminal=False, evaluation="UNCLEAR"),
        monkeypatch,
    )
    session_id = _start("ST404")

    _submit(session_id, "ST404", "TURN-404-1")

    assert _count(session_id, "ST404") == 0


def test_a_turn_still_awaiting_a_submission_is_not_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("AWAITING_SUBMISSION", terminal=False, evaluation="UNCLEAR"),
        monkeypatch,
    )
    session_id = _start("ST405")

    _submit(session_id, "ST405", "TURN-405-1")

    assert _count(session_id, "ST405") == 0


def test_a_voice_attachment_is_evidence_not_an_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A canvas sent alongside speech is evidence for the spoken turn. It has
    already been kept out of the attempt count and the turn identity; the
    counter must not be the one field that lets it back in."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("INDEPENDENTLY_VERIFIED", terminal=True, evaluation="CORRECT"),
        monkeypatch,
    )
    session_id = _start("ST406")

    _submit(
        session_id,
        "ST406",
        "TURN-406-1",
        submission_role="VOICE_ATTACHMENT",
    )

    assert _count(session_id, "ST406") == 0


def test_a_stale_turn_is_not_an_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Work drawn against a question that has already moved on is rejected
    before the tutor sees it, so it cannot have been answered."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("INDEPENDENTLY_VERIFIED", terminal=True, evaluation="CORRECT"),
        monkeypatch,
    )
    session_id = _start("ST407")

    response = _submit(
        session_id,
        "ST407",
        "TURN-407-1",
        canvas_events=[
            {
                "order_index": 0,
                "turn_id": "FRONTEND-LISTENING-TURN",
                "question_id": "Q-A-QUESTION-LONG-GONE",
                "actor": "STUDENT",
                "action_type": "WRITE",
                "content": "Student wrote a line.",
                "math_text": None,
                "target_object_id": "stroke-1",
                "bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
                "semantic_tag": None,
                "source_id": None,
                "active_state": "ACTIVE",
            }
        ],
    )

    assert response.json()["status"] == "STALE_TURN"
    assert _count(session_id, "ST407") == 0


def test_guided_practice_answers_are_not_independent_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of the field: a Guided answer must not inflate it."""

    async def guided(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", guided)
    _pipeline_returning(
        _tutor(None, terminal=False, evaluation="CORRECT"),
        monkeypatch,
    )
    session_id = _start("ST408")

    _submit(session_id, "ST408", "TURN-408-1")

    stored = session_service._get_owned_session(session_id, "ST408")
    assert stored.current_phase == "GUIDED_PRACTICE"
    assert stored.independent_attempt_count == 0


def test_the_session_receipt_reports_the_same_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontend reads the receipt, not the session record. If the mirror
    drifts, the student sees a different number from the one we counted."""

    _phase3_student_model(monkeypatch)
    _pipeline_returning(
        _tutor("RESCUE_REQUIRED", terminal=True, evaluation="INCORRECT"),
        monkeypatch,
    )
    session_id = _start("ST409")
    _submit(session_id, "ST409", "TURN-409-1")

    summary = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST409"},
    )

    assert summary.status_code == 200, summary.text
    performance = summary.json()["session_summary"]["session_performance"]
    assert performance["independent_attempts"] == _count(session_id, "ST409") == 1
    # Not the same thing as the all-phase total, which is what the receipt had
    # to fall back on before.
    assert "total_attempts" in performance
