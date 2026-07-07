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


def test_canvas_planner_circles_the_whole_wrong_line() -> None:
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
    # Marks are line-level: the ellipse is the OCR line box, span is ignored.
    assert ellipse.w == line.w
    assert ellipse.x == line.x + line.w / 2
    assert ellipse.y == line.y + line.h / 2
    assert any(element.kind == "math" and element.text == "x = 9 - 4" for element in elements)
    assert any(element.kind == "arrow" for element in elements)


def test_canvas_planner_emits_circle_only_when_no_correction_intent() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="5",
            target_span=(8, 9),
            replacement_text=None,
            confidence=0.86,
        ),
        [AnnotationIntent(kind="circle_target", target_step_id="step-1")],
    )

    payloads = plan_canvas_draw(tutor, regions)

    assert [element.kind for element in payloads[0].elements] == ["ellipse"]
