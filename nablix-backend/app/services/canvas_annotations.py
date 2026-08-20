import re

from app.ai_engine.classifier_config import FallbackCanvasLabelsConfig
from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    SpatialMathToken,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import CanvasDrawPayload, TutorElement
from app.models.canvas_memory import CanvasEvent
from app.models.guided_learning import TutorCanvasAction
from app.models.question_anchor import QuestionTextAnchor
from app.services.canvas_spatial import canonical_math_token_text


Box = tuple[float, float, float, float]
Point = tuple[float, float]

_TARGET_COLOR = "#E05A47"
_CORRECTION_COLOR = "#175CD3"
_AFFIRMATION_COLOR = "#FFF3A3"

_MATH_EXPRESSION_RE = re.compile(
    r"\b([A-Za-z]\s*[+\-−×*/]\s*(?:[A-Za-z]|\d+))\b"
)
_CHANGING_VALUE_RE = re.compile(
    r"\b([A-Za-z])\s+(?:changes?|varies|can\s+change)\b",
    re.IGNORECASE,
)
_FIXED_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9])([+\-−]?\s*\d+)\s+(?:stays?|is|remains?)\s+(?:fixed|constant)\b",
    re.IGNORECASE,
)
_SYMBOLIC_RULE_RE = re.compile(r"\b([a-z])\s*([+\-−])\s*(\d+)\b", re.IGNORECASE)


def assign_step_ids(regions: list[OCRTextRegion]) -> list[OCRTextRegion]:
    """Return OCR regions with stable step IDs without mutating OCR output."""

    numbered_regions: list[OCRTextRegion] = []
    for index, region in enumerate(regions, start=1):
        step_id = region.step_id or f"step-{index}"
        numbered_regions.append(region.model_copy(update={"step_id": step_id}))
    return numbered_regions


def plan_canvas_draw(
    tutor: TutorResult,
    regions: list[OCRTextRegion],
    spatial_tokens: list[SpatialMathToken] | None = None,
) -> list[CanvasDrawPayload]:
    """Convert grounded tutor annotation intents into frontend draw commands."""

    classification = tutor.mistake_classification
    if classification is None or classification.status != "mistake_found":
        return []

    target_region = _region_for(classification.mistake_step_id, regions)
    if target_region is None:
        return []

    # Without verified token geometry the submission is a broad OCR region only,
    # which localizes as "uncertain": guide in text rather than marking a target
    # the tutor cannot actually point at.
    if not spatial_tokens:
        return []

    if len(classification.target_token_ids) == 0 or classification.error_token is None:
        return _whole_region_draw(tutor, classification, target_region)

    matching_tokens = [
        tok
        for tok in spatial_tokens or []
        if tok.token_id in classification.target_token_ids
    ]
    if (
        len(matching_tokens) != len(classification.target_token_ids)
        or any(token.alignment_confidence < 0.9 for token in matching_tokens)
        or _normalised_token_text(matching_tokens) != _normalised_text(classification.error_token)
    ):
        return []

    boxes = [token.bounding_box for token in matching_tokens if token.bounding_box]
    if len(boxes) != len(matching_tokens):
        return []
    min_x = min(box.get("x", target_region.x) for box in boxes)
    min_y = min(box.get("y", target_region.y) for box in boxes)
    max_x = max(box.get("x", target_region.x) + box.get("width", target_region.w) for box in boxes)
    max_y = max(box.get("y", target_region.y) + box.get("height", target_region.h) for box in boxes)
    target_box: Box = (min_x, min_y, max(0.01, max_x - min_x), max(0.01, max_y - min_y))

    elements = _elements_for(classification, tutor.annotation_intents, target_box)
    if not elements:
        return []

    return [
        CanvasDrawPayload(
            action_id=f"canvas-correction-{target_region.step_id}",
            mode="append",
            elements=elements,
        )
    ]


def plan_confirmed_tutor_draw(
    tutor: TutorResult,
    student_response: str,
    turn_id: str,
) -> list[CanvasDrawPayload]:
    """Write only learner-confirmed ideas in the separate tutor canvas layer.

    Tutor-created maths and labels do not alter learner ink, so they do not
    require OCR token grounding. Exact corrections to learner ink still use
    ``plan_canvas_draw`` and its token-grounding checks.
    """

    if tutor.guided_student_state not in {"CORRECT", "PARTIAL"}:
        return []

    elements: list[TutorElement] = [
        TutorElement(
            id=f"{turn_id}:affirmation-highlight",
            kind="highlight",
            points=[0.58, 0.62, 0.92, 0.62, 0.92, 0.70, 0.58, 0.70],
            color=_AFFIRMATION_COLOR,
            size=18.0,
        ),
        TutorElement(
            id=f"{turn_id}:affirmation",
            kind="text",
            x=0.62,
            y=0.66,
            text="Good thinking — keep this idea.",
            color=_CORRECTION_COLOR,
            size=18.0,
        ),
    ]
    expression_match = _MATH_EXPRESSION_RE.search(student_response)
    if tutor.answer_value_confirmed and expression_match is not None:
        expression = expression_match.group(1).replace("−", "-").replace(" ", "")
        elements.extend(
            [
                TutorElement(
                    id=f"{turn_id}:confirmed-expression",
                    kind="math",
                    x=0.62,
                    y=0.68,
                    tex=expression,
                    color=_CORRECTION_COLOR,
                    size=26.0,
                ),
                TutorElement(
                    id=f"{turn_id}:confirmed-expression-label",
                    kind="text",
                    x=0.62,
                    y=0.74,
                    text="your general rule",
                    color=_CORRECTION_COLOR,
                    size=16.0,
                ),
            ]
        )

    changing_match = _CHANGING_VALUE_RE.search(student_response)
    if changing_match is not None:
        elements.append(
            TutorElement(
                id=f"{turn_id}:changing-label",
                kind="text",
                x=0.62,
                y=0.80,
                text=f"{changing_match.group(1)} → changes",
                color=_CORRECTION_COLOR,
                size=18.0,
            )
        )

    fixed_match = _FIXED_VALUE_RE.search(student_response)
    if fixed_match is not None:
        fixed_value = fixed_match.group(1).replace(" ", "").replace("−", "-")
        elements.append(
            TutorElement(
                id=f"{turn_id}:fixed-label",
                kind="text",
                x=0.62,
                y=0.86,
                text=f"{fixed_value} → stays fixed",
                color=_CORRECTION_COLOR,
                size=18.0,
            )
        )

    if not elements:
        return []
    return [
        CanvasDrawPayload(
            action_id=f"{turn_id}:confirmed-tutor-work",
            mode="append",
            elements=elements,
        )
    ]


def plan_tutor_canvas_actions(
    tutor: TutorResult,
    question_anchors: list[QuestionTextAnchor],
    canvas_events: list[CanvasEvent],
    turn_id: str,
    canonical_answer: str,
    fallback_labels: FallbackCanvasLabelsConfig,
) -> list[TutorCanvasAction]:
    """Validate evaluator intentions against the active Guided Practice state.

    This returns semantic actions only. Coordinates and tutor-layer rendering
    deliberately remain with the frontend. A rejected evaluator intention does
    not affect scoring, progression, or the student canvas.
    """

    active_anchors = {anchor.token_id for anchor in question_anchors}
    active_canvas_objects = {
        event.target_object_id
        for event in canvas_events
        if event.target_object_id is not None and event.active_state == "ACTIVE"
    }
    confirmed = set(
        tutor.active_teaching_objective.confirmed_concept_ids
        if tutor.active_teaching_objective is not None
        else []
    )
    if tutor.guided_teaching_state is not None:
        confirmed.update(tutor.guided_teaching_state.confirmed_component_ids)

    if tutor.requires_written_math_evidence:
        anchor_texts = safe_written_rule_anchors(canonical_answer)
        anchor_actions = [
            TutorCanvasAction(
                action_id=f"{turn_id}:{index}:INSERT_LABEL:TUTOR_ANCHOR",
                type="INSERT_LABEL",
                target_kind="TUTOR_ANCHOR",
                target_object_id=f"TUTOR_ANCHOR:WRITE_RULE:{index}",
                confirmed_component_id=None,
                text=text,
                source_id=None,
                answer_reveal_allowed=False,
            )
            for index, text in enumerate(anchor_texts, start=1)
        ]
        return [
            *anchor_actions,
            TutorCanvasAction(
                action_id=f"{turn_id}:{len(anchor_actions) + 1}:FOCUS:WRITE_AREA",
                type="FOCUS",
                target_kind="WRITE_AREA",
                target_object_id=None,
                confirmed_component_id=None,
                text="Write your rule on the canvas.",
                source_id=None,
                answer_reveal_allowed=False,
            )
        ]

    selected_option_id = (
        tutor.guided_teaching_state.selected_option_id
        if tutor.guided_teaching_state is not None
        else None
    )
    selected_option_action = (
        TutorCanvasAction(
            action_id=f"{turn_id}:1:HIGHLIGHT:QUESTION_OPTION:{selected_option_id}",
            type="HIGHLIGHT",
            target_kind="QUESTION_OPTION",
            target_object_id=(
                f"{tutor.guided_teaching_state.question_id}:OPTION:{selected_option_id}"
                if tutor.guided_teaching_state is not None
                else None
            ),
            confirmed_component_id=next(iter(sorted(confirmed)), None),
            text=None,
            source_id=None,
            answer_reveal_allowed=False,
        )
        if selected_option_id is not None and tutor.guided_teaching_state is not None
        else None
    )

    if tutor.guided_student_state == "WRONG":
        if selected_option_action is not None:
            return [selected_option_action]
        student_attempt = next(
            (
                event.target_object_id
                for event in reversed(canvas_events)
                if event.actor == "STUDENT"
                and event.action_type == "WRITE"
                and event.active_state == "ACTIVE"
                and event.target_object_id is not None
            ),
            None,
        )
        if student_attempt is None:
            return []
        return [
            TutorCanvasAction(
                action_id=f"{turn_id}:1:HIGHLIGHT:{student_attempt}",
                type="HIGHLIGHT",
                target_kind="STUDENT_ATTEMPT",
                target_object_id=student_attempt,
                confirmed_component_id=None,
                text=None,
                source_id=None,
                answer_reveal_allowed=False,
            )
        ]

    if tutor.guided_student_state == "STUCK":
        target = question_anchors[0].token_id if question_anchors else None
        return [
            TutorCanvasAction(
                action_id=f"{turn_id}:1:FOCUS:{target or 'NONE'}",
                type="FOCUS",
                target_kind="QUESTION_ANCHOR" if target is not None else "TUTOR_ANCHOR",
                target_object_id=target,
                confirmed_component_id=None,
                text="Start with this part.",
                source_id=None,
                answer_reveal_allowed=False,
            )
        ]

    if tutor.guided_student_state not in {"CORRECT", "PARTIAL"}:
        return []

    actions: list[TutorCanvasAction] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for position, intention in enumerate(tutor.canvas_intentions, start=1):
        if intention.action_type in {"TUTOR_SOLVED_STEP", "SHOW_CUE", "OPEN_SCAFFOLD_STEP", "SHOW_PARALLEL"}:
            continue
        if intention.confirmed_component_id is not None and intention.confirmed_component_id not in confirmed:
            continue
        if intention.target_kind == "QUESTION_ANCHOR":
            target_is_valid = intention.target_object_id in active_anchors
        elif intention.target_kind in {"CANVAS_OBJECT", "STUDENT_ATTEMPT"}:
            target_is_valid = intention.target_object_id in active_canvas_objects
        else:
            target_is_valid = intention.target_kind == "TUTOR_ANCHOR" and intention.target_object_id is None
        if not target_is_valid:
            continue
        text = intention.text.strip() if intention.text is not None else None
        if text is not None and canonical_answer.casefold() in text.casefold():
            continue
        key = (intention.action_type, intention.target_object_id, text)
        if key in seen:
            continue
        seen.add(key)
        action_id = f"{turn_id}:{position}:{intention.action_type}:{intention.target_object_id or 'NONE'}"
        if any(event.source_id == action_id and event.active_state == "ACTIVE" for event in canvas_events):
            continue
        actions.append(
            TutorCanvasAction(
                action_id=action_id,
                type=intention.action_type,
                target_kind=intention.target_kind,
                target_object_id=intention.target_object_id,
                confirmed_component_id=intention.confirmed_component_id,
                text=text,
                source_id=intention.source_id,
                answer_reveal_allowed=False,
            )
        )
    if not actions and selected_option_action is not None:
        actions.append(selected_option_action)
    if not actions:
        actions = fallback_confirmation_actions(
            tutor,
            question_anchors,
            canvas_events,
            turn_id,
            canonical_answer,
            fallback_labels,
        )
    return add_confirmation_canvas_slots(actions, turn_id)


def add_confirmation_canvas_slots(
    actions: list[TutorCanvasAction],
    turn_id: str,
) -> list[TutorCanvasAction]:
    """Pair confirmed question labels with persistent tutor-layer canvas notes."""

    slot_actions = [
        TutorCanvasAction(
            action_id=f"{turn_id}:CONFIRMED_SLOT:{index}",
            type="INSERT_LABEL",
            target_kind="TUTOR_ANCHOR",
            target_object_id=(
                f"TUTOR_ANCHOR:CONFIRMED:{question_id_for_anchor(action.target_object_id)}:{index}"
            ),
            confirmed_component_id=action.confirmed_component_id,
            text=action.text,
            source_id=None,
            answer_reveal_allowed=False,
        )
        for index, action in enumerate(actions, start=1)
        if action.type == "INSERT_LABEL"
        and action.target_kind == "QUESTION_ANCHOR"
        and action.confirmed_component_id is not None
        and action.text is not None
    ]
    return [*actions, *slot_actions]


def question_id_for_anchor(target_object_id: str | None) -> str:
    if target_object_id is None or ":QTOKEN:" not in target_object_id:
        raise ValueError("Confirmed canvas labels must target a question anchor.")
    return target_object_id.split(":QTOKEN:", maxsplit=1)[0]


def fallback_confirmation_actions(
    tutor: TutorResult,
    question_anchors: list[QuestionTextAnchor],
    canvas_events: list[CanvasEvent],
    turn_id: str,
    canonical_answer: str,
    labels: FallbackCanvasLabelsConfig,
) -> list[TutorCanvasAction]:
    """Render already-confirmed meanings when evaluator actions are absent."""

    confirmed = confirmed_component_ids(tutor)
    if not confirmed:
        return []
    parts = _SYMBOLIC_RULE_RE.search(canonical_answer)
    if parts is None:
        return generic_confirmation_actions(
            tutor,
            question_anchors,
            canvas_events,
            turn_id,
            confirmed,
            labels,
        )
    variable, operator, fixed_value = parts.groups()
    normalised_operator = "+" if operator == "+" else "-"
    actions: list[TutorCanvasAction] = []
    for component_id in sorted(confirmed):
        role = confirmation_role(component_id, tutor)
        targets: list[QuestionTextAnchor] = []
        text_template = labels.generic
        text_values: dict[str, str] = {}
        if role == "changing_value":
            targets = [anchor for anchor in question_anchors if anchor.text == variable]
            if not targets:
                targets = [
                    anchor
                    for anchor in question_anchors
                    if anchor.text.isdigit() and anchor.text != fixed_value
                ]
            text_template = labels.changing_value
        elif role == "fixed_value":
            targets = [anchor for anchor in question_anchors if anchor.text == fixed_value]
            text_template = labels.fixed_value
        elif role == "operation":
            targets = [
                anchor
                for anchor in question_anchors
                if anchor.text.replace("−", "-") == normalised_operator
            ]
            text_template = labels.operation
            text_values["operation"] = labels.operation_names.get(
                normalised_operator,
                "the operation",
            )
        else:
            targets = generic_component_targets(component_id, tutor, question_anchors)
        for target in targets:
            text = text_template.format(value=target.text, **text_values)
            if active_confirmation_exists(
                canvas_events,
                component_id,
                target.token_id,
                text,
            ):
                continue
            position = len(actions) + 1
            actions.append(
                TutorCanvasAction(
                    action_id=(
                        f"{turn_id}:{position}:INSERT_LABEL:{target.token_id}"
                    ),
                    type="INSERT_LABEL",
                    target_kind="QUESTION_ANCHOR",
                    target_object_id=target.token_id,
                    confirmed_component_id=component_id,
                    text=text,
                    source_id=None,
                    answer_reveal_allowed=False,
                )
            )
    return actions


def confirmed_component_ids(tutor: TutorResult) -> set[str]:
    confirmed = set(
        tutor.active_teaching_objective.confirmed_concept_ids
        if tutor.active_teaching_objective is not None
        else []
    )
    if tutor.guided_teaching_state is not None:
        confirmed.update(tutor.guided_teaching_state.confirmed_component_ids)
        confirmed.update(tutor.guided_teaching_state.completed_step_ids)
    return confirmed


def generic_confirmation_actions(
    tutor: TutorResult,
    question_anchors: list[QuestionTextAnchor],
    canvas_events: list[CanvasEvent],
    turn_id: str,
    confirmed: set[str],
    labels: FallbackCanvasLabelsConfig,
) -> list[TutorCanvasAction]:
    """Label confirmed concepts when the authored answer is not an expression."""

    actions: list[TutorCanvasAction] = []
    for component_id in sorted(confirmed):
        for target in generic_component_targets(component_id, tutor, question_anchors):
            text = labels.generic.format(value=target.text)
            if active_confirmation_exists(
                canvas_events,
                component_id,
                target.token_id,
                text,
            ):
                continue
            position = len(actions) + 1
            actions.append(
                TutorCanvasAction(
                    action_id=(
                        f"{turn_id}:{position}:INSERT_LABEL:{target.token_id}"
                    ),
                    type="INSERT_LABEL",
                    target_kind="QUESTION_ANCHOR",
                    target_object_id=target.token_id,
                    confirmed_component_id=component_id,
                    text=text,
                    source_id=None,
                    answer_reveal_allowed=False,
                )
            )
    return actions


def confirmation_role(component_id: str, tutor: TutorResult) -> str:
    description = next(
        (
            concept.description
            for concept in (
                tutor.generated_question_rubric.required_concepts
                if tutor.generated_question_rubric is not None
                else []
            )
            if concept.concept_id == component_id
        ),
        "",
    )
    source = f"{component_id} {description}".casefold()
    if any(term in source for term in ("changing", "variable", "varies")):
        return "changing_value"
    if any(term in source for term in ("fixed", "constant", "stays")):
        return "fixed_value"
    if any(term in source for term in ("operation", "addition", "subtract", "multiply", "divide")):
        return "operation"
    return "generic"


def generic_component_targets(
    component_id: str,
    tutor: TutorResult,
    question_anchors: list[QuestionTextAnchor],
) -> list[QuestionTextAnchor]:
    description = next(
        (
            concept.description
            for concept in (
                tutor.generated_question_rubric.required_concepts
                if tutor.generated_question_rubric is not None
                else []
            )
            if concept.concept_id == component_id
        ),
        "",
    )
    words = {word.casefold() for word in re.findall(r"[A-Za-z0-9]+", description)}
    return [anchor for anchor in question_anchors if anchor.text.casefold() in words]


def active_confirmation_exists(
    canvas_events: list[CanvasEvent],
    component_id: str,
    target_object_id: str,
    text: str,
) -> bool:
    return any(
        event.actor == "TUTOR"
        and event.action_type == "INSERT_LABEL"
        and event.semantic_tag == component_id
        and event.target_object_id == target_object_id
        and event.content == text
        and event.active_state == "ACTIVE"
        for event in canvas_events
    )


def safe_written_rule_anchors(canonical_answer: str) -> list[str]:
    """Expose separate authored rule parts, never the unresolved expression."""

    match = _SYMBOLIC_RULE_RE.search(canonical_answer)
    if match is None:
        return []
    variable, operator, value = match.groups()
    normalised_operator = "+" if operator == "+" else "-"
    operation_label = "Gain" if normalised_operator == "+" else "Change"
    return [f"Start: {variable}", f"{operation_label}: {normalised_operator}{value}"]


def plan_write_request_tutor_draw(turn_id: str) -> list[CanvasDrawPayload]:
    """Point to a tutor-layer writing area without supplying the answer."""

    return [
        CanvasDrawPayload(
            action_id=f"{turn_id}:write-request",
            mode="append",
            elements=[
                TutorElement(
                    id=f"{turn_id}:write-highlight",
                    kind="highlight",
                    points=[0.58, 0.62, 0.92, 0.62, 0.92, 0.74, 0.58, 0.74],
                    color=_AFFIRMATION_COLOR,
                    size=18.0,
                ),
                TutorElement(
                    id=f"{turn_id}:write-prompt",
                    kind="text",
                    x=0.62,
                    y=0.66,
                    text="Write your rule here.",
                    color=_CORRECTION_COLOR,
                    size=18.0,
                ),
                TutorElement(
                    id=f"{turn_id}:write-arrow",
                    kind="arrow",
                    from_=[0.75, 0.56],
                    to=[0.75, 0.62],
                    color=_CORRECTION_COLOR,
                    stroke_width=2.0,
                ),
            ],
        )
    ]


def _whole_region_draw(
    tutor: TutorResult,
    classification: TutorMistakeClassification,
    region: OCRTextRegion,
) -> list[CanvasDrawPayload]:
    intents = [
        intent
        for intent in tutor.annotation_intents
        if intent.target_step_id == classification.mistake_step_id
    ]
    if (
        classification.target_span is not None
        or classification.replacement_text is not None
        or _normalised_text(classification.target_text or "")
        != _normalised_text(region.text)
        or len(intents) != 1
        or intents[0].kind != "circle_target"
    ):
        return []
    return [
        CanvasDrawPayload(
            action_id=f"canvas-line-review-{region.step_id}",
            mode="append",
            elements=[
                _ellipse_element((region.x, region.y, region.w, region.h), 1)
            ],
        )
    ]



def _region_for(step_id: str | None, regions: list[OCRTextRegion]) -> OCRTextRegion | None:
    if step_id is None:
        return None
    for region in regions:
        if region.step_id == step_id:
            return region
    return None


def _normalised_text(value: str) -> str:
    return canonical_math_token_text(value)


def _normalised_token_text(tokens: list[SpatialMathToken]) -> str:
    return "".join(_normalised_text(token.text) for token in tokens)


def _elements_for(
    classification: TutorMistakeClassification,
    intents: list[AnnotationIntent],
    target_box: Box,
) -> list[TutorElement]:
    matching_intents = [
        intent
        for intent in intents
        if intent.target_step_id == classification.mistake_step_id
    ]
    correction_center = _correction_center_for(target_box, matching_intents)

    elements: list[TutorElement] = []
    for index, intent in enumerate(matching_intents, start=1):
        if intent.kind == "circle_target":
            elements.append(_ellipse_element(target_box, index))
        if intent.kind == "write_correction":
            correction_text = intent.text or classification.replacement_text
            if correction_text:
                elements.append(_correction_element(correction_text, correction_center, index))
        if intent.kind == "draw_arrow":
            # Edge-to-edge, not centre-to-centre: starting inside the circle and
            # ending on top of the correction text buries the arrowhead in the "=".
            x, y, w, h = target_box
            start = (_clamp(x + w + 0.005, 0.0, 1.0), _clamp(y + h / 2, 0.0, 1.0))
            end = (_clamp(correction_center[0] - 0.055, 0.0, 1.0), correction_center[1])
            elements.append(_arrow_element(start, end, index))
    return elements


def _correction_center_for(target_box: Box, intents: list[AnnotationIntent]) -> Point:
    placement = "right"
    for intent in intents:
        if intent.kind == "write_correction" and intent.placement is not None:
            placement = intent.placement
            break
    return _placed_correction_center(target_box, placement)


def _placed_correction_center(target_box: Box, placement: str) -> Point:
    x, y, w, h = target_box
    center_x = x + w / 2
    center_y = y + h / 2
    if placement == "below" or x + w + 0.22 > 1.0:
        return (_clamp(center_x, 0.08, 0.92), _clamp(y + h + 0.09, 0.08, 0.94))
    return (_clamp(x + w + 0.14, 0.08, 0.92), _clamp(center_y, 0.08, 0.94))


def _ellipse_element(target_box: Box, index: int) -> TutorElement:
    x, y, w, h = target_box
    center_x = x + w / 2
    center_y = y + h / 2
    return TutorElement(
        id=f"mistake-circle-{index}",
        kind="ellipse",
        x=_clamp(center_x, 0.0, 1.0),
        y=_clamp(center_y, 0.0, 1.0),
        w=_clamp(w, 0.0, 1.0),
        h=_clamp(h, 0.0, 1.0),
        color=_TARGET_COLOR,
        stroke_width=3.0,
    )


def _correction_element(text: str, center: Point, index: int) -> TutorElement:
    return TutorElement(
        id=f"mistake-correction-{index}",
        kind="math",
        x=center[0],
        y=center[1],
        text=text,
        color=_CORRECTION_COLOR,
        size=24.0,
    )


def _arrow_element(start: Point, end: Point, index: int) -> TutorElement:
    return TutorElement(
        id=f"mistake-arrow-{index}",
        kind="arrow",
        from_=[start[0], start[1]],
        to=[end[0], end[1]],
        color=_CORRECTION_COLOR,
        stroke_width=2.0,
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
