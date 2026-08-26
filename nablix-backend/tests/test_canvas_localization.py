from typing import NamedTuple

import pytest

from app.ai_engine.canvas_localization import localize_math_difference
from app.ai_engine.canvas_math_review import review_canvas_math
from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.schemas import CanvasTextRegion
from app.models.adapters import SpatialMathToken


class TokenSpec(NamedTuple):
    text: str
    role: str = "unknown"


def _tokens(*specs: TokenSpec) -> list[SpatialMathToken]:
    return [
        SpatialMathToken(
            token_id=f"step-1:token-{index}",
            step_id="step-1",
            text=spec.text,
            role=spec.role,
            semantic_path=f"/math/token[{index}]",
            bounding_box={
                "x": index / 10,
                "y": 0.2,
                "width": 0.05,
                "height": 0.08,
            },
            alignment_confidence=0.95,
        )
        for index, spec in enumerate(specs, start=1)
    ]


def _step_tokens(step_id: str, *specs: TokenSpec) -> list[SpatialMathToken]:
    return [
        SpatialMathToken(
            token_id=f"{step_id}:token-{index}",
            step_id=step_id,
            text=spec.text,
            role=spec.role,
            semantic_path=f"/math/token[{index}]",
            bounding_box={
                "x": index / 10,
                "y": 0.2,
                "width": 0.05,
                "height": 0.08,
            },
            alignment_confidence=0.95,
        )
        for index, spec in enumerate(specs, start=1)
    ]


@pytest.mark.parametrize(
    ("expected", "actual", "actual_specs", "target_id", "target_text"),
    [
        ("c+4", "c-4", ("c", "-", "4"), "step-1:token-2", "-"),
        ("c+4", "c+5", ("c", "+", "5"), "step-1:token-3", "5"),
        ("x+4", "y+4", ("y", "+", "4"), "step-1:token-1", "y"),
        ("12x+40", "12x+45", ("12", "x", "+", "45"), "step-1:token-4", "45"),
        ("x-4", "x+4", ("x", "+", "4"), "step-1:token-2", "+"),
        ("x²", "x³", ("x", "3"), "step-1:token-2", "3"),
        ("3/4", "3/5", ("3", "/", "5"), "step-1:token-3", "5"),
        ("2(x+3)", "2(x-3)", ("2", "(", "x", "-", "3", ")"), "step-1:token-4", "-"),
        ("x+x+3", "x+x+4", ("x", "+", "x", "+", "4"), "step-1:token-5", "4"),
    ],
)
def test_localizes_one_semantic_token_difference(
    expected: str,
    actual: str,
    actual_specs: tuple[str, ...],
    target_id: str,
    target_text: str,
) -> None:
    result = localize_math_difference(
        expected_text=expected,
        actual_text=actual,
        actual_tokens=_tokens(*(TokenSpec(text) for text in actual_specs)),
    )

    assert result is not None
    assert result.localization_level == "TOKEN"
    assert result.target_token_ids == (target_id,)
    assert result.actual_text == target_text


def test_localizes_unicode_operator_difference() -> None:
    result = localize_math_difference(
        expected_text="c+4",
        actual_text="c − 4",
        actual_tokens=_tokens(TokenSpec("c"), TokenSpec("−", "operator"), TokenSpec("4", "number")),
    )

    assert result is not None
    assert result.target_token_ids == ("step-1:token-2",)
    assert result.actual_text == "−"
    assert result.expected_text == "+"


def test_localizes_latex_fraction_difference() -> None:
    result = localize_math_difference(
        expected_text=r"\frac{3}{4}",
        actual_text="3/5",
        actual_tokens=_tokens(
            TokenSpec("3", "fraction_numerator"),
            TokenSpec("/", "fraction_bar"),
            TokenSpec("5", "fraction_denominator"),
        ),
    )

    assert result is not None
    assert result.target_token_ids == ("step-1:token-3",)
    assert result.actual_text == "5"
    assert result.expected_text == "4"


def test_exposes_geometry_fallback_without_losing_semantic_target() -> None:
    result = localize_math_difference(
        expected_text="c+4",
        actual_text="c-4",
        actual_tokens=[
            SpatialMathToken(
                token_id="step-1:token-1",
                step_id="step-1",
                text="c",
                bounding_box={"x": 0.1, "y": 0.2, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-2",
                step_id="step-1",
                text="-",
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-3",
                step_id="step-1",
                text="4",
                bounding_box={"x": 0.3, "y": 0.2, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
        ],
    )

    assert result.localization_level == "TOKEN"
    assert result.target_token_ids == ("step-1:token-2",)
    assert result.actual_text == "-"
    assert result.fallback_reason == "TOKEN_GEOMETRY_UNAVAILABLE"


def test_does_not_conflate_missing_unary_minus_with_binary_subtraction() -> None:
    result = localize_math_difference(
        expected_text="-4",
        actual_text="4",
        actual_tokens=_tokens(TokenSpec("4", "number")),
    )

    assert result is not None
    assert result.localization_level == "STEP"
    assert result.target_token_ids == ()
    assert result.fallback_reason == "MISSING_EXPECTED_TOKEN"


def test_localizes_equation_value_token() -> None:
    result = localize_math_difference(
        expected_text="2x+3=7",
        actual_text="2x+4=7",
        actual_tokens=_tokens(
            TokenSpec("2", "number"),
            TokenSpec("x", "identifier"),
            TokenSpec("+", "operator"),
            TokenSpec("4", "number"),
            TokenSpec("=", "operator"),
            TokenSpec("7", "number"),
        ),
    )

    assert result is not None
    assert result.target_token_ids == ("step-1:token-4",)
    assert result.semantic_path == "/math/token[4]"


def test_returns_span_for_multiple_tokens_in_one_structural_difference() -> None:
    result = localize_math_difference(
        expected_text="2x+7",
        actual_text="2x-9",
        actual_tokens=_tokens(
            TokenSpec("2", "number"),
            TokenSpec("x", "identifier"),
            TokenSpec("-", "operator"),
            TokenSpec("9", "number"),
        ),
    )

    assert result is not None
    assert result.localization_level == "SPAN"
    assert result.target_token_ids == ("step-1:token-3", "step-1:token-4")
    assert result.actual_text == "-9"
    assert result.expected_text == "+7"


def test_returns_no_difference_for_equivalent_normalized_math() -> None:
    result = localize_math_difference(
        expected_text="c-4",
        actual_text="c − 4",
        actual_tokens=_tokens(TokenSpec("c"), TokenSpec("−", "operator"), TokenSpec("4", "number")),
    )

    assert result is None


def test_review_exposes_precise_localization_metadata() -> None:
    review = review_canvas_math(
        question="Write the expression.",
        correct_answer="c+4",
        current_phase="GUIDED_PRACTICE",
        canvas_regions=[
            CanvasTextRegion(
                step_id="step-1",
                text="c - 4",
                x=0.1,
                y=0.2,
                w=0.4,
                h=0.1,
                confidence=0.99,
            )
        ],
        spatial_tokens=_tokens(
            TokenSpec("c", "identifier"),
            TokenSpec("-", "operator"),
            TokenSpec("4", "number"),
        ),
        config=load_classifier_rules().canvas_review,
        confidence=0.99,
    )

    classification = review.mistake_classification
    assert classification.localization_level == "TOKEN"
    assert classification.target_token_ids == ["step-1:token-2"]
    assert classification.target_span == [2, 3]
    assert classification.semantic_path == "/math/token[2]"
    assert classification.fallback_reason is None


def test_multipart_missing_text_does_not_mark_correct_math_expression() -> None:
    review = review_canvas_math(
        question="State the rule and what changes.",
        correct_answer="c+4",
        current_phase="GUIDED_PRACTICE",
        canvas_regions=[
            CanvasTextRegion(
                step_id="step-1",
                text="c + 4",
                x=0.1,
                y=0.2,
                w=0.4,
                h=0.1,
                confidence=0.99,
            )
        ],
        spatial_tokens=_tokens(
            TokenSpec("c", "identifier"),
            TokenSpec("+", "operator"),
            TokenSpec("4", "number"),
        ),
        config=load_classifier_rules().canvas_review,
        confidence=0.99,
    )

    assert review.mistake_classification.status == "no_mistake"


def test_review_localizes_independent_practice_without_emitting_tutor_ink() -> None:
    review = review_canvas_math(
        question="Write the expression.",
        correct_answer="c+4",
        current_phase="INDEPENDENT_PRACTICE",
        canvas_regions=[
            CanvasTextRegion(
                step_id="step-1",
                text="c - 4",
                x=0.1,
                y=0.2,
                w=0.4,
                h=0.1,
                confidence=0.99,
            )
        ],
        spatial_tokens=_tokens(
            TokenSpec("c", "identifier"),
            TokenSpec("-", "operator"),
            TokenSpec("4", "number"),
        ),
        config=load_classifier_rules().canvas_review,
        confidence=0.99,
    )

    assert review.mistake_classification.localization_level == "TOKEN"
    assert review.mistake_classification.target_token_ids == [
        "step-1:token-2"
    ]
    assert review.annotation_intents == []


@pytest.mark.xfail(
    strict=True,
    reason="Slice 4 wires localization into _mistake_review; remove this marker then.",
)
def test_review_selects_first_incorrect_step_before_localizing_its_token() -> None:
    review = review_canvas_math(
        question="x + 4 = 9",
        correct_answer="x = 5",
        current_phase="GUIDED_PRACTICE",
        canvas_regions=[
            CanvasTextRegion(
                step_id="step-1",
                text="x + 4 = 9",
                x=0.1,
                y=0.1,
                w=0.4,
                h=0.1,
                confidence=0.99,
            ),
            CanvasTextRegion(
                step_id="step-2",
                text="x = 9 - 5",
                x=0.1,
                y=0.3,
                w=0.4,
                h=0.1,
                confidence=0.99,
            ),
            CanvasTextRegion(
                step_id="step-3",
                text="x = 4",
                x=0.1,
                y=0.5,
                w=0.4,
                h=0.1,
                confidence=0.99,
            ),
        ],
        spatial_tokens=_step_tokens(
            "step-2",
            TokenSpec("x", "identifier"),
            TokenSpec("=", "operator"),
            TokenSpec("9", "number"),
            TokenSpec("-", "operator"),
            TokenSpec("5", "number"),
        ),
        config=load_classifier_rules().canvas_review,
        confidence=0.99,
    )

    classification = review.mistake_classification
    assert classification.mistake_step_id == "step-2"
    assert classification.target_token_ids == ["step-2:token-5"]
    assert classification.error_token == "5"
    assert classification.localization_level == "TOKEN"


def test_review_localizes_structural_direct_difference_as_span() -> None:
    review = review_canvas_math(
        question="Write the expression.",
        correct_answer="n+5",
        current_phase="GUIDED_PRACTICE",
        canvas_regions=[
            CanvasTextRegion(
                step_id="step-1",
                text="n - 7",
                x=0.1,
                y=0.2,
                w=0.4,
                h=0.1,
                confidence=0.99,
            )
        ],
        spatial_tokens=_tokens(
            TokenSpec("n", "identifier"),
            TokenSpec("-", "operator"),
            TokenSpec("7", "number"),
        ),
        config=load_classifier_rules().canvas_review,
        confidence=0.99,
    )

    classification = review.mistake_classification
    assert classification.localization_level == "SPAN"
    assert classification.target_token_ids == [
        "step-1:token-2",
        "step-1:token-3",
    ]
    assert classification.fallback_reason is None


def test_review_uses_step_fallback_for_separate_semantic_differences() -> None:
    result = localize_math_difference(
        expected_text="2x+7",
        actual_text="2y+9",
        actual_tokens=_tokens(
            TokenSpec("2", "number"),
            TokenSpec("y", "identifier"),
            TokenSpec("+", "operator"),
            TokenSpec("9", "number"),
        ),
    )

    assert result is not None
    assert result.localization_level == "STEP"
    assert result.fallback_reason == "MULTIPLE_SEMANTIC_DIFFERENCES"
