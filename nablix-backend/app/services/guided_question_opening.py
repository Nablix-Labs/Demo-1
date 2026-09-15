from __future__ import annotations

import re
from typing import Final

from app.models.guided_learning import TutorCanvasAction
from app.models.question_anchor import QuestionTextAnchor
from app.models.student_model_session import QuestionOption, QuestionType
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
_TRAILING_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:as|and annotate|then|after|for comparison)\b", re.IGNORECASE
)
_CLAUSE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"\band\b", re.IGNORECASE)
_IN_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"\s+in\s+", re.IGNORECASE)
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
    options: list[QuestionOption] | None = None,
) -> tuple[list[QuestionTextAnchor], list[TutorCanvasAction], str | None]:
    """Compile a safe subset of authored start actions against served content.

    Grounded against the question text AND its structured options. A choice
    question is served with its stem split from its options, so an authored
    action naming an option ("highlight n + 4" on Q-T01-004) matched nothing in
    the stem and was rejected on every turn. An option target becomes the
    QUESTION_OPTION action the client already renders, never invented geometry.
    """
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
    option_actions = [
        TutorCanvasAction(
            action_id=f"AUTHORED:{question_id}:OPTION:{option.option_id}:HIGHLIGHT",
            type="HIGHLIGHT",
            target_kind="QUESTION_OPTION",
            target_object_id=f"{question_id}:OPTION:{option.option_id}",
            confirmed_component_id=None,
            text=None,
            source_id="question_guided_start_prompts",
        )
        for option in _authored_target_options(options, action_text)
    ]
    if not targets and not option_actions:
        return anchors, [], "authored_canvas_targets_not_in_question"
    label = _annotation_label(action_text)
    # A choice is evidence only after the learner has made it. Opening-time
    # highlights for both options make the tutor appear to reveal the answer
    # and are not durable across the learner's later confirmation.
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


def _authored_clauses(canvas_action: str) -> list[str]:
    """The action's `<target> in <context>` clauses, in authored order.

    Q-T01-004's authored action is "Highlight n in n+4 and 12 in 12+4 for
    comparison": TWO clauses, each naming a token and the option it lives in.
    Read as one flat phrase it collapsed to "n" and both contexts were lost,
    which is why nothing matched and the action was rejected on every turn.
    """
    lowered = canvas_action.casefold()
    for prefix in ("group/highlight", "focus/highlight", "highlight"):
        if lowered.startswith(prefix):
            body = canvas_action[len(prefix):]
            break
    else:
        body = canvas_action
    # Trailing instructions first, so "and annotate" cannot be mistaken for the
    # "and" that joins two clauses.
    body = _TRAILING_CLAUSE_RE.split(body, maxsplit=1)[0]
    return [clause for clause in _CLAUSE_SPLIT_RE.split(body) if clause.strip()]


def _tokens_of(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _ACTION_TOKEN_RE.finditer(text)}


def _authored_target_options(
    options: list[QuestionOption] | None,
    canvas_action: str,
) -> list[QuestionOption]:
    """Options the action names, through the `in <context>` half of its clauses.

    Matched context-inside-option, never the reverse: the served option text
    carries whatever the stem parser left on it -- Q-T01-004's option A arrives
    as "12 + 4 or" -- so requiring the option to be a subset of the action would
    drop a perfectly good match. A context with no word or number in it is
    ignored, so a bare operator cannot select every option.
    """
    contexts: list[set[str]] = []
    for clause in _authored_clauses(canvas_action):
        context = _tokens_of(_IN_SPLIT_RE.split(clause, maxsplit=1)[-1])
        if any(token.isalnum() for token in context):
            contexts.append(context)
    return [
        option
        for option in options or []
        if any(context <= _tokens_of(option.text) for context in contexts)
    ]


def _authored_target_tokens(canvas_action: str) -> set[str]:
    """Question-text tokens the action points at: each clause's `in` target."""
    tokens: set[str] = set()
    for clause in _authored_clauses(canvas_action):
        tokens |= _tokens_of(_IN_SPLIT_RE.split(clause, maxsplit=1)[0])
    return tokens - {"only", "the", "four", "terms", "together"}


def _annotation_label(canvas_action: str) -> str | None:
    lowered = canvas_action.casefold()
    if "annotate" not in lowered and " as " not in lowered:
        return None
    for marker, label in _ANNOTATION_LABELS:
        if marker in lowered:
            return label
    return None
