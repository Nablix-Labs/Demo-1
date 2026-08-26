import json
from pathlib import Path
import re

from app.ai_engine.canvas_localization import localize_math_difference
from app.models.adapters import SpatialMathToken


QUESTION_BANK_PATH = Path(__file__).parents[1] / "app/services/rag/question_serving/question_bank.json"


def _question_bank() -> list[dict[str, str]]:
    payload: object = json.loads(QUESTION_BANK_PATH.read_text())
    if not isinstance(payload, list):
        raise AssertionError("Question bank must be a list")
    questions: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in item.items()
        ):
            raise AssertionError("Question bank entries must be string mappings")
        questions.append({key: value for key, value in item.items()})
    return questions


def _wrong_answer(answer: str) -> str:
    match = list(re.finditer(r"\d+", answer))[-1]
    value = int(match.group(0)) + 1
    return f"{answer[:match.start()]}{value}{answer[match.end():]}"


def _tokens(step_id: str, text: str) -> list[SpatialMathToken]:
    return [
        SpatialMathToken(
            token_id=f"{step_id}:token-{index}",
            step_id=step_id,
            text=token,
            bounding_box={
                "x": index / 10,
                "y": 0.2,
                "width": 0.05,
                "height": 0.08,
            },
            alignment_confidence=0.95,
        )
        for index, token in enumerate(
            re.findall(r"\d+(?:\.\d*)?|[A-Za-z]+|[()+\-*/=]", text),
            start=1,
        )
    ]


def test_question_bank_categories_have_a_localization_path() -> None:
    questions = _question_bank()
    categories = {(question["phase"], question["subtopic"]) for question in questions}

    assert len(questions) == 30
    assert categories == {
        ("DIAGNOSTIC", "One-Step Equations"),
        ("CONCEPT_ORIENTATION", "One-Step Equations"),
        ("GUIDED_PRACTICE", "One-Step Equations"),
        ("INDEPENDENT_PRACTICE", "One-Step Equations"),
        ("REVIEW", "One-Step Equations"),
        ("DIAGNOSTIC", "Two-Step Equations"),
        ("CONCEPT_ORIENTATION", "Two-Step Equations"),
        ("GUIDED_PRACTICE", "Two-Step Equations"),
        ("INDEPENDENT_PRACTICE", "Two-Step Equations"),
        ("REVIEW", "Two-Step Equations"),
    }

    for question in questions:
        actual = _wrong_answer(question["correct_answer"])
        localization = localize_math_difference(
            expected_text=question["correct_answer"],
            actual_text=actual,
            actual_tokens=_tokens("step-1", actual),
        )
        assert localization is not None, question["question_id"]
        assert localization.target_token_ids, question["question_id"]
