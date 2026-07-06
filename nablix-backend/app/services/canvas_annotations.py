from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import CanvasDrawPayload, TutorElement


Box = tuple[float, float, float, float]
Point = tuple[float, float]

_DRAW_CONFIDENCE_THRESHOLD = 0.75
_TARGET_COLOR = "#E05A47"
_CORRECTION_COLOR = "#175CD3"


def assign_step_ids(regions: list[OCRTextRegion]) -> list[OCRTextRegion]:
    """Return OCR regions with stable step IDs without mutating OCR output."""

    numbered_regions: list[OCRTextRegion] = []
    for index, region in enumerate(regions, start=1):
        step_id = region.step_id or f"step-{index}"
        numbered_regions.append(region.model_copy(update={"step_id": step_id}))
    return numbered_regions


def plan_canvas_draw(tutor: TutorResult, regions: list[OCRTextRegion]) -> list[CanvasDrawPayload]:
    """Convert grounded tutor annotation intents into frontend draw commands."""

    classification = tutor.mistake_classification
    if classification is None or classification.status != "mistake_found":
        return []

    target_region = _region_for(classification.mistake_step_id, regions)
    if target_region is None:
        return []

    target_box = _target_box_for(classification, target_region)
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


def _region_for(step_id: str | None, regions: list[OCRTextRegion]) -> OCRTextRegion | None:
    if step_id is None:
        return None
    for region in regions:
        if region.step_id == step_id:
            return region
    return None


def _target_box_for(classification: TutorMistakeClassification, region: OCRTextRegion) -> Box:
    if _has_valid_span(classification, region):
        return _span_box(classification, region)
    return _line_box(region)


def _has_valid_span(classification: TutorMistakeClassification, region: OCRTextRegion) -> bool:
    if classification.confidence < _DRAW_CONFIDENCE_THRESHOLD:
        return False
    if classification.target_span is None or classification.target_text is None:
        return False

    start, end = classification.target_span
    if start < 0 or end <= start or end > len(region.text):
        return False
    return region.text[start:end] == classification.target_text


def _span_box(classification: TutorMistakeClassification, region: OCRTextRegion) -> Box:
    if classification.target_span is None:
        return _line_box(region)

    start, end = classification.target_span
    text_length = len(region.text)
    if text_length == 0:
        return _line_box(region)

    raw_x = region.x + region.w * start / text_length
    raw_w = region.w * (end - start) / text_length
    pad_x = max(raw_w * 0.6, 0.012)
    x = _clamp(raw_x - pad_x, region.x, region.x + region.w)
    right = _clamp(raw_x + raw_w + pad_x, region.x, region.x + region.w)
    w = right - x
    minimum_w = min(region.w, 0.035)
    if w < minimum_w:
        center_x = _clamp(
            raw_x + raw_w / 2,
            region.x + minimum_w / 2,
            region.x + region.w - minimum_w / 2,
        )
        x = center_x - minimum_w / 2
        w = minimum_w
    return (x, region.y, w, region.h)


def _line_box(region: OCRTextRegion) -> Box:
    return (region.x, region.y, region.w, region.h)


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
            elements.append(_arrow_element(_center_of(target_box), correction_center, index))
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


def _center_of(box: Box) -> Point:
    x, y, w, h = box
    return (_clamp(x + w / 2, 0.0, 1.0), _clamp(y + h / 2, 0.0, 1.0))


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))
