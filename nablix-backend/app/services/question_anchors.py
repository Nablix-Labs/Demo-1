"""Stable anchors into the question text the learner is reading.

The question is rendered by the frontend, not drawn on the canvas, so the
backend has no geometry for it and must not invent any. What it can give is a
stable identity and an exact character span per token: the frontend renders the
same string, so it can resolve a span to a position precisely.

This is the question-text counterpart of the canvas token contract - a mark is
only ever offered for a token that really occurs in the text that was served.
"""

import re

from app.models.question_anchor import QuestionTextAnchor
from app.models.student_model_session import AnswerSpec


# One token per word, number, or standalone symbol, with its offsets kept.
_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+|[+\-−×÷*/=]")

_CHANGING_LABEL = "changes"
_FIXED_LABEL = "stays fixed"

# Mirrors the guided controller's expression contract: "c + 4" -> c, +, 4.
_EXPRESSION_RE = re.compile(r"\b([a-z])\s*([+\-−×x*])\s*(\d+)\b")


def question_text_tokens(
    question_id: str,
    question_text: str,
) -> list[QuestionTextAnchor]:
    """Assign a stable ID and character span to every token in the question."""

    return [
        QuestionTextAnchor(
            token_id=f"{question_id}:QTOKEN:{index}",
            text=match.group(0),
            char_start=match.start(),
            char_end=match.end(),
        )
        for index, match in enumerate(_TOKEN_RE.finditer(question_text), start=1)
    ]


def plan_question_anchors(
    question_id: str | None,
    question_text: str | None,
    answer_spec: AnswerSpec | None,
    active_step_id: str | None,
) -> list[QuestionTextAnchor]:
    """Anchor the part of the question the active teaching step is about.

    The step is chosen by the guided controller, so the anchor follows the
    lesson rather than a model's guess at what to point out.
    """

    if question_id is None or not question_text or active_step_id is None:
        return []
    if answer_spec is None:
        return []
    parts = _EXPRESSION_RE.search(answer_spec.canonical_answer.casefold())
    if parts is None:
        return []
    variable, _operator, fixed_value = parts.groups()

    tokens = question_text_tokens(question_id, question_text)
    if active_step_id == "CHANGING_VALUE":
        # Case-sensitive: a lowercase variable never opens a sentence, so this
        # keeps the article "A" from being read as the variable "a".
        named = [token for token in tokens if token.text == variable]
        # A question that never names the variable still shows the learner
        # concrete starting values; those are what varies between cases.
        targets = named or [
            token for token in tokens if token.text.isdigit() and token.text != fixed_value
        ]
        return [token.model_copy(update={"label": _CHANGING_LABEL}) for token in targets]

    if active_step_id == "FIXED_VALUE":
        return [
            token.model_copy(update={"label": _FIXED_LABEL})
            for token in tokens
            if token.text == fixed_value
        ]

    return []


def plan_canvas_action_anchors(
    question_id: str | None,
    question_text: str | None,
) -> list[QuestionTextAnchor]:
    """Expose stable question tokens for post-evaluation tutor annotations."""

    if question_id is None or not question_text:
        return []
    return question_text_tokens(question_id, question_text)
