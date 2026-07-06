from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import TutorElement
from app.services.canvas_annotations import assign_step_ids, plan_canvas_draw


def _tutor_result(
    classification: TutorMistakeClassification,
    annotation_intents: list[AnnotationIntent],
) -> TutorResult:
    return TutorResult(
        evaluation="INCORRECT",
        error_type="ARITHMETIC_ERROR",
        intent="SUBMITTING_ANSWER",
        response_strategy="GUIDED_HINT",
        tutor_message="Subtract 4, not 5.",
        tutor_message_voice="Subtract 4, not 5.",
        voice_optimised=True,
        hint_level=1,
        answer_reveal_allowed=False,
        confidence=0.9,
        input_source="CANVAS",
        mistake_classification=classification,
        annotation_intents=annotation_intents,
    )


def _region() -> OCRTextRegion:
    return OCRTextRegion(
        text="x = 9 - 5",
        x=0.12,
        y=0.30,
        w=0.34,
        h=0.08,
        confidence=0.95,
    )


def _intents() -> list[AnnotationIntent]:
    return [
        AnnotationIntent(kind="circle_target", target_step_id="step-1"),
        AnnotationIntent(
            kind="write_correction",
            target_step_id="step-1",
            text="x = 9 - 4",
            placement="right",
        ),
        AnnotationIntent(kind="draw_arrow", target_step_id="step-1"),
    ]


def _ellipse_from(elements: list[TutorElement]) -> TutorElement:
    ellipse = next(element for element in elements if element.kind == "ellipse")
    assert ellipse.x is not None
    assert ellipse.w is not None
    return ellipse


def test_canvas_planner_uses_valid_target_span() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="5",
            target_span=(8, 9),
            replacement_text="4",
            confidence=0.86,
        ),
        _intents(),
    )

    payloads = plan_canvas_draw(tutor, regions)

    assert len(payloads) == 1
    elements = payloads[0].elements
    ellipse = _ellipse_from(elements)
    line = regions[0]
    assert ellipse.w < line.w
    assert ellipse.x - ellipse.w / 2 >= line.x
    assert ellipse.x + ellipse.w / 2 <= line.x + line.w + 1e-12
    assert any(element.kind == "math" and element.text == "x = 9 - 4" for element in elements)
    assert any(element.kind == "arrow" for element in elements)


def test_canvas_planner_uses_whole_line_when_target_text_mismatches_span() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="4",
            target_span=(8, 9),
            replacement_text="4",
            confidence=0.86,
        ),
        _intents(),
    )

    payloads = plan_canvas_draw(tutor, regions)

    ellipse = _ellipse_from(payloads[0].elements)
    assert ellipse.w == regions[0].w


def test_canvas_planner_uses_whole_line_when_confidence_is_low() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="5",
            target_span=(8, 9),
            replacement_text="4",
            confidence=0.74,
        ),
        _intents(),
    )

    payloads = plan_canvas_draw(tutor, regions)

    ellipse = _ellipse_from(payloads[0].elements)
    assert ellipse.w == regions[0].w
