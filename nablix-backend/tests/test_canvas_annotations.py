from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    SpatialMathToken,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import TutorElement
from app.services.canvas_annotations import (
    assign_step_ids,
    plan_canvas_draw,
    plan_confirmed_tutor_draw,
)


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
        attempt_increment=1,
        recommended_conversation_action="GIVE_HINT",
        question_completed=False,
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


def _token() -> SpatialMathToken:
    return SpatialMathToken(
        token_id="step-1:token-1",
        step_id="step-1",
        text="x",
        bounding_box={"x": 0.12, "y": 0.30, "width": 0.05, "height": 0.08},
        alignment_confidence=0.95,
    )


def _ellipse_from(elements: list[TutorElement]) -> TutorElement:
    ellipse = next(element for element in elements if element.kind == "ellipse")
    assert ellipse.x is not None
    assert ellipse.w is not None
    return ellipse


def test_canvas_planner_does_not_mark_without_grounded_tokens() -> None:
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

    assert plan_canvas_draw(tutor, regions) == []


def test_canvas_planner_does_not_mark_without_grounded_tokens_when_no_correction_intent() -> None:
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

    assert plan_canvas_draw(tutor, regions) == []


def test_canvas_planner_circles_explicit_whole_line_mistake() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="x = 9 - 5",
            target_span=None,
            replacement_text=None,
            confidence=0.95,
        ),
        [AnnotationIntent(kind="circle_target", target_step_id="step-1")],
    )

    draw = plan_canvas_draw(tutor, regions, [_token()])

    assert len(draw) == 1
    assert draw[0].action_id == "canvas-line-review-step-1"
    assert [element.kind for element in draw[0].elements] == ["ellipse"]


def test_canvas_planner_uses_target_token_geometry() -> None:
    regions = assign_step_ids(
        [
            OCRTextRegion(
                text="c - 4",
                x=0.10,
                y=0.30,
                w=0.40,
                h=0.08,
                confidence=0.95,
            )
        ]
    )
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_token_ids=["step-1:token-2"],
            error_token="-",
            expected_token="+",
            target_text="-",
            replacement_text="+",
            confidence=0.95,
        ),
        [
            AnnotationIntent(kind="circle_target", target_step_id="step-1"),
            AnnotationIntent(
                kind="write_correction",
                target_step_id="step-1",
                text="+",
                placement="right",
            ),
            AnnotationIntent(kind="draw_arrow", target_step_id="step-1"),
        ],
    )
    draw = plan_canvas_draw(
        tutor,
        regions,
        [
            SpatialMathToken(
                token_id="step-1:token-1",
                step_id="step-1",
                text="c",
                bounding_box={"x": 0.10, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-2",
                step_id="step-1",
                text="-",
                bounding_box={"x": 0.20, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-3",
                step_id="step-1",
                text="4",
                bounding_box={"x": 0.30, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
        ],
    )

    assert [element.kind for element in draw[0].elements] == [
        "ellipse",
        "math",
        "arrow",
    ]
    assert abs(draw[0].elements[0].w - 0.05) < 1e-9
    assert abs(draw[0].elements[0].h - 0.08) < 1e-9
