from types import SimpleNamespace
from typing import cast

from app.models.adapters import TutorResult
from app.models.session import SessionRecord
from app.services.interaction_service import _require_authored_canvas_confirmation


def _confirmed_tutor() -> TutorResult:
    return TutorResult.model_construct(
        evaluation="CORRECT",
        response_strategy="ADVANCE",
        tutor_message="You have described the rule clearly.",
        tutor_message_voice="You have described the rule clearly.",
        answer_value_confirmed=True,
        question_completed=True,
        reasoning_complete=True,
        requires_written_math_evidence=False,
        attempt_increment=0,
        recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION",
    )


def test_authored_canvas_requirement_preserves_tutor_reply_and_stops_progression() -> None:
    session = cast(
        SessionRecord,
        SimpleNamespace(
            canvas_submission_required=True,
            pending_canvas_submission_question_id=None,
            question_id="Q-T01-001",
        ),
    )

    result = _require_authored_canvas_confirmation(
        session,
        _confirmed_tutor(),
        False,
    )

    assert result.tutor_message.startswith("You have described the rule clearly.")
    assert result.write_instruction == "You have the rule. Now write it on the canvas, then press Check."
    assert result.requires_written_math_evidence is True
    assert result.question_completed is False
    assert result.answer_value_confirmed is True


def test_question_without_authored_canvas_requirement_is_unchanged() -> None:
    session = cast(SessionRecord, SimpleNamespace(canvas_submission_required=False))
    tutor = _confirmed_tutor()

    assert _require_authored_canvas_confirmation(session, tutor, False) is tutor


def test_complete_canvas_submission_allows_the_tutor_to_progress() -> None:
    session = cast(SessionRecord, SimpleNamespace(canvas_submission_required=True))
    tutor = _confirmed_tutor()

    assert _require_authored_canvas_confirmation(session, tutor, True) is tutor


def test_pending_canvas_keeps_the_tutor_reply_without_repeating_the_instruction() -> None:
    session = cast(
        SessionRecord,
        SimpleNamespace(
            canvas_submission_required=True,
            pending_canvas_submission_question_id="Q-T01-001",
            question_id="Q-T01-001",
        ),
    )

    result = _require_authored_canvas_confirmation(session, _confirmed_tutor(), False)

    assert result.tutor_message == "You have described the rule clearly."
    assert result.write_instruction == "You have the rule. Now write it on the canvas, then press Check."
