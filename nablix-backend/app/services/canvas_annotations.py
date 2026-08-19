import re

from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    SpatialMathToken,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import CanvasDrawPayload, TutorElement
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
            x=0.58,
            y=0.62,
            w=0.34,
            h=0.08,
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
                    x=0.58,
                    y=0.62,
                    w=0.34,
                    h=0.12,
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
