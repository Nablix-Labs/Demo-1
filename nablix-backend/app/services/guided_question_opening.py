from __future__ import annotations

import re
from typing import Final

from app.models.guided_learning import TutorCanvasAction
from app.models.question_anchor import QuestionTextAnchor
from app.models.student_model_session import QuestionType
from app.services.question_anchors import question_text_tokens


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
_ACTION_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z]+|\d+|[+\-−×÷*/=]")
_ANNOTATION_LABELS: Final[tuple[tuple[str, str], ...]] = (
    ("stays fixed", "stays fixed"),
    ("fixed", "stays fixed"),
    ("starting", "starting value"),
    ("changing", "changes"),
    ("variable", "can change"),
)


def guided_question_opening(
    question: str,
    question_type: QuestionType | None,
    lead_in: str,
    tutor_prompt: str | None,
) -> str:
    cleaned_question = question.strip()
    if cleaned_question == "":
        raise ValueError("Guided question opening requires non-empty question text.")
    spoken_question = (
        cleaned_question
        if cleaned_question.endswith((".", "?", "!"))
        else f"{cleaned_question}."
    )
    authored_prompt = tutor_prompt.strip() if tutor_prompt is not None else ""
    motivation = (
        authored_prompt
        if authored_prompt != ""
        else _MOTIVATION_BY_QUESTION_TYPE[question_type]
        if question_type is not None
        else _DEFAULT_MOTIVATION
    )
    parts = [lead_in.strip(), spoken_question, motivation]
    return " ".join(part for part in parts if part != "")


def authored_question_opening_actions(
    question_id: str | None,
    question_text: str | None,
    canvas_action: str | None,
) -> tuple[list[QuestionTextAnchor], list[TutorCanvasAction], str | None]:
    """Compile a safe subset of authored start actions against served text."""
    if question_id is None or question_text is None or canvas_action is None:
        return [], [], None
    action_text = canvas_action.strip()
    if action_text == "":
        return [], [], None
    anchors = question_text_tokens(question_id, question_text)
    if not action_text.casefold().startswith(("highlight", "group/highlight", "focus/highlight")):
        return anchors, [], "unsupported_authored_canvas_action"
    if "after response" in action_text.casefold():
        return anchors, [], "deferred_authored_canvas_action"
    target_tokens = _authored_target_tokens(action_text)
    targets = [
        anchor
        for anchor in anchors
        if anchor.text.casefold() in target_tokens
    ]
    if not targets:
        return anchors, [], "authored_canvas_targets_not_in_question"
    label = _annotation_label(action_text)
    actions: list[TutorCanvasAction] = []
    for anchor in targets:
        prefix = f"AUTHORED:{question_id}:{anchor.token_id}"
        actions.append(TutorCanvasAction(
            action_id=f"{prefix}:HIGHLIGHT",
            type="HIGHLIGHT",
            target_kind="QUESTION_ANCHOR",
            target_object_id=anchor.token_id,
            confirmed_component_id=None,
            text=None,
            source_id="question_guided_start_prompts",
        ))
        if label is not None:
            actions.append(TutorCanvasAction(
                action_id=f"{prefix}:LABEL",
                type="INSERT_LABEL",
                target_kind="QUESTION_ANCHOR",
                target_object_id=anchor.token_id,
                confirmed_component_id=None,
                text=label,
                source_id="question_guided_start_prompts",
            ))
    return anchors, actions, None


def _authored_target_tokens(canvas_action: str) -> set[str]:
    lowered = canvas_action.casefold()
    if lowered.startswith("group/highlight"):
        target = canvas_action[len("group/highlight"):]
    elif lowered.startswith("focus/highlight"):
        target = canvas_action[len("focus/highlight"):]
    else:
        target = canvas_action[len("highlight"):]
    target = re.split(r"\b(?:as|and annotate|then|after|for comparison)\b", target, maxsplit=1, flags=re.IGNORECASE)[0]
    if " in " in target.casefold():
        target = target.split(" in ", 1)[0]
    tokens = {match.group(0).casefold() for match in _ACTION_TOKEN_RE.finditer(target)}
    return tokens - {"only", "the", "four", "terms", "together"}


def _annotation_label(canvas_action: str) -> str | None:
    lowered = canvas_action.casefold()
    if "annotate" not in lowered and " as " not in lowered:
        return None
    for marker, label in _ANNOTATION_LABELS:
        if marker in lowered:
            return label
    return None
