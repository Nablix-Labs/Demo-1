from typing import Final

from app.models.student_model_session import QuestionType


_MOTIVATION_BY_QUESTION_TYPE: Final[dict[QuestionType, str]] = {
    "SINGLE_CHOICE": (
        "Look through the choices carefully—you already know enough to make a start."
    ),
    "SHORT_RESPONSE": "Take your time and begin with what you notice.",
    "MULTI_PART_SHORT_RESPONSE": (
        "Take it one part at a time—you do not have to solve every part at once."
    ),
    "CHOICE_WITH_EXPLANATION": (
        "Choose the option that fits best, then talk me through your thinking."
    ),
    "TRUE_FALSE_WITH_EXPLANATION": (
        "Decide whether it is true or false, then tell me what convinced you."
    ),
}
_DEFAULT_MOTIVATION: Final[str] = "Take your time and start with what you notice."


def guided_question_opening(
    question: str,
    question_type: QuestionType | None,
    lead_in: str,
) -> str:
    cleaned_question = question.strip()
    if cleaned_question == "":
        raise ValueError("Guided question opening requires non-empty question text.")
    spoken_question = (
        cleaned_question
        if cleaned_question.endswith((".", "?", "!"))
        else f"{cleaned_question}."
    )
    motivation = (
        _MOTIVATION_BY_QUESTION_TYPE[question_type]
        if question_type is not None
        else _DEFAULT_MOTIVATION
    )
    parts = [lead_in.strip(), spoken_question, motivation]
    return " ".join(part for part in parts if part != "")
