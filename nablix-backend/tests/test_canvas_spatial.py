"""Unit tests for the Spatial Overlay Engine and character-level token bounding box planning."""

from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import CanvasPoint, CanvasStroke
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


def test_align_step_tokens_and_plan_canvas_draw() -> None:
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


_CMINUS4 = "<math><mi>c</mi><mo>-</mo><mn>4</mn></math>"
_LINE = OCRTextRegion(text="c-4", step_id="step-1", x=0.10, y=0.30, w=0.40, h=0.08, confidence=0.95)


def _symbol_boxes() -> list[OCRTextRegion]:
    return [
        OCRTextRegion(text="c", x=0.10, y=0.31, w=0.05, h=0.06, confidence=0.95),
        OCRTextRegion(text="-", x=0.20, y=0.33, w=0.04, h=0.01, confidence=0.94),
        OCRTextRegion(text="4", x=0.30, y=0.31, w=0.05, h=0.06, confidence=0.96),
    ]


def _stroke(stroke_id: str, x0: float, x1: float) -> CanvasStroke:
    return CanvasStroke(
        stroke_id=stroke_id,
        tool="pen",
        points=[CanvasPoint(x=x0, y=0.32), CanvasPoint(x=x1, y=0.34)],
        width=0.01,
    )


def test_stroke_clusters_are_not_trusted_when_they_do_not_match_the_symbols() -> None:
    """Joining 'c-' into one stroke shifts every later pairing.

    Positional pairing would hand token '-' the geometry of whatever was written
    third, at grounded confidence: a confident circle around the wrong symbol.
    """

    tokens = align_step_tokens(
        "step-1",
        _CMINUS4,
        "c-4",
        [_stroke("s1", 0.11, 0.24), _stroke("s2", 0.31, 0.34)],
        _LINE,
    )

    assert [token.text for token in tokens] == ["c", "-", "4"]
    assert all(token.alignment_confidence < 0.9 for token in tokens)


def test_ocr_symbol_boxes_localize_tokens_without_any_strokes() -> None:
    """A snapshot-only submission still gets per-symbol geometry from OCR."""

    tokens = align_step_tokens("step-1", _CMINUS4, "c-4", [], _LINE, _symbol_boxes())

    minus = next(token for token in tokens if token.text == "-")
    assert minus.alignment_confidence >= 0.9
    assert minus.bounding_box["width"] < _LINE.w
    assert minus.bounding_box["x"] == 0.20


def test_ocr_symbol_boxes_are_rejected_when_they_disagree_with_the_symbols() -> None:
    disagreeing = _symbol_boxes()[:2]

    tokens = align_step_tokens("step-1", _CMINUS4, "c-4", [], _LINE, disagreeing)

    assert all(token.alignment_confidence < 0.9 for token in tokens)
