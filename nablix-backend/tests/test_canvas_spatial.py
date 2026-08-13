"""Unit tests for the Spatial Overlay Engine and character-level token bounding box planning."""

import pytest

from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import CanvasPoint, CanvasStroke
from app.services import canvas_annotations
from app.services.canvas_annotations import plan_canvas_draw
from app.services.canvas_spatial import (
    align_step_tokens,
    associate_strokes_with_steps,
    group_strokes_into_candidates,
    parse_mathml_tokens,
)


def test_parse_mathml_tokens() -> None:
    mathml = """
    <math>
      <mrow>
        <mn>4</mn>
        <mo>-</mo>
        <mi>y</mi>
        <mo>=</mo>
        <mn>10</mn>
      </mrow>
    </math>
    """
    tokens = parse_mathml_tokens(mathml)
    assert len(tokens) == 5
    assert tokens[0].text == "4" and tokens[0].role == "number"
    assert tokens[1].text == "-" and tokens[1].role == "operator"
    assert tokens[2].text == "y" and tokens[2].role == "identifier"
    assert tokens[3].text == "=" and tokens[3].role == "operator"
    assert tokens[4].text == "10" and tokens[4].role == "number"


def test_associate_strokes_with_steps() -> None:
    region_step1 = OCRTextRegion(step_id="step-1", text="4 - y = 10", x=0.1, y=0.1, w=0.5, h=0.1, confidence=0.9)
    stroke1 = CanvasStroke(
        stroke_id="stroke-1",
        tool="pen",
        points=[CanvasPoint(x=0.2, y=0.12), CanvasPoint(x=0.22, y=0.12)],
    )
    result = associate_strokes_with_steps([stroke1], [region_step1])
    assert "step-1" in result
    assert len(result["step-1"]) == 1
    assert result["step-1"][0].stroke_id == "stroke-1"


def test_associate_strokes_uses_the_stroke_vertical_bounds() -> None:
    first = OCRTextRegion(step_id="step-1", text="x=5", x=0.1, y=0.1, w=0.5, h=0.1, confidence=0.9)
    second = OCRTextRegion(step_id="step-2", text="x=6", x=0.1, y=0.5, w=0.5, h=0.1, confidence=0.9)
    stroke = CanvasStroke(
        stroke_id="stroke-2",
        tool="pen",
        points=[CanvasPoint(x=0.95, y=0.52), CanvasPoint(x=0.98, y=0.54)],
    )

    result = associate_strokes_with_steps([stroke], [first, second])

    assert result["step-2"] == [stroke]


def test_group_strokes_into_candidates() -> None:
    # Two parallel horizontal strokes close together forming '='
    stroke_equals_top = CanvasStroke(
        stroke_id="s-eq-1",
        tool="pen",
        points=[CanvasPoint(x=0.3, y=0.2), CanvasPoint(x=0.35, y=0.2)],
    )
    stroke_equals_bottom = CanvasStroke(
        stroke_id="s-eq-2",
        tool="pen",
        points=[CanvasPoint(x=0.3, y=0.22), CanvasPoint(x=0.35, y=0.22)],
    )
    candidates = group_strokes_into_candidates([stroke_equals_top, stroke_equals_bottom])
    assert len(candidates) == 1
    assert len(candidates[0]) == 2


def test_align_step_tokens_and_plan_canvas_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    mathml = "<math><mrow><mn>4</mn><mo>-</mo><mi>y</mi></mrow></math>"
    s1 = CanvasStroke(stroke_id="s1", tool="pen", points=[CanvasPoint(x=0.1, y=0.1), CanvasPoint(x=0.12, y=0.12)])  # 4
    s2 = CanvasStroke(stroke_id="s2", tool="pen", points=[CanvasPoint(x=0.2, y=0.1), CanvasPoint(x=0.25, y=0.1)])   # -
    s3 = CanvasStroke(stroke_id="s3", tool="pen", points=[CanvasPoint(x=0.3, y=0.1), CanvasPoint(x=0.32, y=0.15)])  # y

    spatial_tokens = align_step_tokens("step-1", mathml, "4-y", [s1, s2, s3])
    assert len(spatial_tokens) == 3
    minus_token = spatial_tokens[1]
    assert minus_token.token_id == "step-1:token-2"
    assert minus_token.text == "-"

    # Test plan_canvas_draw resolving token-2
    tutor_res = TutorResult(
        evaluation="INCORRECT",
        error_type="OPPOSITE_OPERATION",
        intent="CANVAS_EVAL",
        response_strategy="CORRECT_MISTAKE",
        tutor_message="Check your sign",
        tutor_message_voice="Check your sign",
        voice_optimised=True,
        hint_level=1,
        answer_reveal_allowed=False,
        confidence=0.95,
        input_source="CANVAS",
        recommended_conversation_action="GIVE_HINT",
        question_completed=False,
        attempt_increment=1,
        mistake_classification=TutorMistakeClassification(

            status="mistake_found",
            mistake_step_id="step-1",
            target_token_ids=["step-1:token-2"],
            error_token="-",
            expected_token="+",
            confidence=0.95,
        ),
        annotation_intents=[
            AnnotationIntent(kind="circle_target", target_step_id="step-1"),
        ],
    )

    regions = [OCRTextRegion(step_id="step-1", text="4-y", x=0.0, y=0.0, w=0.5, h=0.2, confidence=0.9)]
    # V1 never draws on student ink, so exercise the retained grounding explicitly
    # rather than letting it rot unexercised while dormant.
    assert plan_canvas_draw(tutor_res, regions, spatial_tokens) == []
    monkeypatch.setattr(canvas_annotations, "_ANNOTATE_STUDENT_INK", True)
    payloads = plan_canvas_draw(tutor_res, regions, spatial_tokens)
    assert len(payloads) == 1
    assert len(payloads[0].elements) == 1
    elem = payloads[0].elements[0]
    assert elem.kind == "ellipse"
    # Verify the circle center is around x=0.225 (bounding box of minus stroke s2)
    assert 0.18 <= elem.x <= 0.28


def test_plan_canvas_draw_omits_uncertain_token_alignment() -> None:
    tutor_res = TutorResult(
        evaluation="INCORRECT",
        error_type="OPPOSITE_OPERATION",
        intent="CANVAS_EVAL",
        response_strategy="CORRECT_MISTAKE",
        tutor_message="Check your sign",
        tutor_message_voice="Check your sign",
        voice_optimised=True,
        hint_level=1,
        answer_reveal_allowed=False,
        confidence=0.95,
        input_source="CANVAS",
        recommended_conversation_action="GIVE_HINT",
        question_completed=False,
        attempt_increment=1,
        mistake_classification=TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_token_ids=["step-1:token-2"],
            error_token="-",
            expected_token="+",
            confidence=0.95,
        ),
        annotation_intents=[AnnotationIntent(kind="circle_target", target_step_id="step-1")],
    )
    regions = [OCRTextRegion(step_id="step-1", text="4-y", x=0.0, y=0.0, w=0.5, h=0.2, confidence=0.9)]

    payloads = plan_canvas_draw(tutor_res, regions, [])

    assert payloads == []
