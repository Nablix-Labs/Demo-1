import pytest

from app.models.student_model_session import QuestionType
from app.services.guided_question_opening import guided_question_opening


@pytest.mark.parametrize(
    ("question_type", "expected_motivation"),
    [
        (
            "MULTI_PART_SHORT_RESPONSE",
            "Take it one part at a time—you do not have to solve every part at once.",
        ),
        (
            "CHOICE_WITH_EXPLANATION",
            "Choose the option that fits best, then talk me through your thinking.",
        ),
        (
            "SHORT_RESPONSE",
            "Take your time and begin with what you notice.",
        ),
    ],
)
def test_guided_question_opening_combines_question_and_motivation(
    question_type: QuestionType,
    expected_motivation: str,
) -> None:
    message = guided_question_opening(
        "What changes and what stays fixed?",
        question_type,
        "Let us try one together.",
    )

    assert message == (
        "Let us try one together. What changes and what stays fixed? "
        f"{expected_motivation}"
    )


def test_guided_question_opening_rejects_missing_question_text() -> None:
    with pytest.raises(ValueError, match="non-empty question text"):
        guided_question_opening("   ", "SHORT_RESPONSE", "Let us begin.")
