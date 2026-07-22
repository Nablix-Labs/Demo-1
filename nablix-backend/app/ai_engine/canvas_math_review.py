from __future__ import annotations

import re
from functools import lru_cache

from lark import Lark, Token, Tree
from lark.exceptions import LarkError
from sympy import Add, Eq, Expr, Mul, Poly, Rational, S, Symbol, solveset
from sympy.core.relational import Equality
from sympy.polys.polyerrors import PolynomialError
from sympy.sets.sets import Set

from app.ai_engine.classifier_config import CanvasReviewConfig
from app.ai_engine.schemas import (
    CanvasAnnotationIntent,
    CanvasFeedback,
    CanvasMathReview,
    CanvasMistakeClassification,
    CanvasStepFeedback,
    CanvasTextRegion,
    ErrorType,
    HighlightInstruction,
    LearningPhase,
)


_EQUATION_GRAMMAR = r"""
    ?start: equation
    equation: expression "=" expression
    ?expression: expression "+" term   -> add
               | expression "-" term   -> subtract
               | term
    ?term: term "*" unary              -> multiply
         | term "/" unary              -> divide
         | unary
    ?unary: "-" unary                  -> negate
          | "+" unary                  -> positive
          | atom
    ?atom: NUMBER                       -> number
         | VARIABLE                     -> variable
         | "(" expression ")"
    NUMBER: /(?:\d+(?:\.\d*)?|\.\d+)/
    VARIABLE: /[A-Za-z]/
    %import common.WS_INLINE
    %ignore WS_INLINE
"""

_SYMBOL_FOLLOWER = re.compile(r"(?<=[0-9A-Za-z)])(?=[A-Za-z(])")
_NUMBER_AFTER_SYMBOL = re.compile(r"(?<=[A-Za-z)])(?=\d)")
_SIMPLE_FRACTION = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_FINAL_ANSWER = re.compile(r"^\s*[A-Za-z]\s*=\s*-?(?:\d+(?:\.\d*)?|\.\d+)\s*$")
_BINARY_NUMERIC_OPERATION = re.compile(
    r"([+-])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)
_ISOLATED_NUMERIC_VALUE = re.compile(
    r"=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)


class CanvasMathParseError(ValueError):
    """Raised when OCR text is outside the supported equation grammar."""


def normalize_canvas_math_text(text: str) -> str:
    """Return parser-ready math text without evaluating OCR-controlled input."""

    normalized: str = text.strip()
    replacements: tuple[tuple[str, str], ...] = (
        ("−", "-"),
        ("–", "-"),
        ("—", "-"),
        ("×", "*"),
        ("·", "*"),
        ("÷", "/"),
        (r"\times", "*"),
        (r"\cdot", "*"),
        (r"\div", "/"),
        (r"\left", ""),
        (r"\right", ""),
        (r"\(", ""),
        (r"\)", ""),
        ("$", ""),
        ("{", "("),
        ("}", ")"),
    )
    while _SIMPLE_FRACTION.search(normalized) is not None:
        normalized = _SIMPLE_FRACTION.sub(r"(\1)/(\2)", normalized)
    for source, replacement in replacements:
        normalized = normalized.replace(source, replacement)
    normalized = _SYMBOL_FOLLOWER.sub("*", normalized)
    normalized = _NUMBER_AFTER_SYMBOL.sub("*", normalized)
    return " ".join(normalized.split())


def review_canvas_math(
    question: str,
    correct_answer: str,
    current_phase: LearningPhase,
    canvas_regions: list[CanvasTextRegion],
    config: CanvasReviewConfig,
    confidence: float,
) -> CanvasMathReview:
    """Find the first OCR equation step that changes the original solution set."""

    uncertain: CanvasMathReview = _uncertain_review(confidence)
    if len(canvas_regions) == 0:
        return uncertain
    if any(
        region.confidence < config.min_region_confidence or "?" in region.text
        for region in canvas_regions
    ):
        return uncertain

    try:
        original_equation, variable = _parse_original_equation(
            question,
            config.max_expression_characters,
        )
        expected_solutions: Set = _solution_set(original_equation, variable)
        parsed_steps: list[Equality] = [
            _parse_step_equation(
                region.text,
                variable,
                config.max_expression_characters,
            )
            for region in canvas_regions
        ]
        _validate_expected_answer(
            correct_answer,
            variable,
            expected_solutions,
            config.max_expression_characters,
        )
    except CanvasMathParseError:
        return uncertain

    previous_equation: Equality = original_equation
    previous_solutions: Set = expected_solutions
    for index, (region, equation) in enumerate(zip(canvas_regions, parsed_steps)):
        try:
            current_solutions: Set = _solution_set(equation, variable)
        except CanvasMathParseError:
            return uncertain
        if current_solutions != previous_solutions:
            return _mistake_review(
                index=index,
                region=region,
                previous_equation=previous_equation,
                current_equation=equation,
                variable=variable,
                correct_answer=correct_answer,
                current_phase=current_phase,
                canvas_regions=canvas_regions,
                config=config,
                confidence=confidence,
            )
        previous_equation = equation
        previous_solutions = current_solutions

    return CanvasMathReview(
        error_type=None,
        tutor_feedback=None,
        canvas_feedback=_correct_step_feedback(canvas_regions, current_phase, config),
        mistake_classification=CanvasMistakeClassification(
            status="no_mistake",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=confidence,
        ),
        annotation_intents=[],
    )


@lru_cache(maxsize=1)
def _equation_parser() -> Lark:
    return Lark(_EQUATION_GRAMMAR, parser="lalr", start="start")


def _parse_original_equation(text: str, max_characters: int) -> tuple[Equality, Symbol]:
    equation_text: str = text.rsplit(":", maxsplit=1)[-1] if ":" in text else text
    equation: Equality = _parse_equation(equation_text, None, max_characters)
    symbols: set[Symbol] = equation.free_symbols
    if len(symbols) != 1:
        raise CanvasMathParseError("The question must contain exactly one variable.")
    variable: Symbol = next(iter(symbols))
    _validate_linear_equation(equation, variable)
    return equation, variable


def _parse_step_equation(text: str, variable: Symbol, max_characters: int) -> Equality:
    normalized: str = normalize_canvas_math_text(text)
    if "=" not in normalized:
        normalized = f"{variable} = {normalized}"
    equation: Equality = _parse_equation(normalized, variable, max_characters)
    _validate_linear_equation(equation, variable)
    return equation


def _parse_equation(
    text: str,
    expected_variable: Symbol | None,
    max_characters: int,
) -> Equality:
    normalized: str = normalize_canvas_math_text(text)
    if len(normalized) == 0 or len(normalized) > max_characters:
        raise CanvasMathParseError("The equation text is empty or too long.")
    try:
        tree: Tree[Token] = _equation_parser().parse(normalized)
        if tree.data != "equation" or len(tree.children) != 2:
            raise CanvasMathParseError("The OCR line is not one equation.")
        left: Expr = _expression_from_tree(tree.children[0], expected_variable)
        right: Expr = _expression_from_tree(tree.children[1], expected_variable)
    except (LarkError, TypeError, ValueError, ZeroDivisionError) as error:
        raise CanvasMathParseError(f"Unable to parse equation: {normalized}") from error
    equation: Equality = Eq(left, right, evaluate=False)
    if expected_variable is not None and not equation.free_symbols.issubset({expected_variable}):
        raise CanvasMathParseError("The equation contains an unexpected variable.")
    return equation


def _expression_from_tree(node: Tree[Token] | Token, expected_variable: Symbol | None) -> Expr:
    if isinstance(node, Token):
        raise CanvasMathParseError(f"Unexpected token: {node}")
    if node.data == "number":
        return Rational(str(node.children[0]))
    if node.data == "variable":
        name: str = str(node.children[0]).lower()
        if expected_variable is not None and name != expected_variable.name:
            raise CanvasMathParseError(f"Unexpected variable: {name}")
        return Symbol(name, real=True)
    if node.data == "positive":
        return _expression_from_tree(node.children[0], expected_variable)
    if node.data == "negate":
        return Mul(-1, _expression_from_tree(node.children[0], expected_variable))

    left: Expr = _expression_from_tree(node.children[0], expected_variable)
    right: Expr = _expression_from_tree(node.children[1], expected_variable)
    if node.data == "add":
        return Add(left, right)
    if node.data == "subtract":
        return Add(left, Mul(-1, right))
    if node.data == "multiply":
        return Mul(left, right)
    if node.data == "divide":
        if right == 0:
            raise CanvasMathParseError("Division by zero is not supported.")
        return Mul(left, right**-1)
    raise CanvasMathParseError(f"Unsupported expression node: {node.data}")


def _validate_linear_equation(equation: Equality, variable: Symbol) -> None:
    residual: Expr = equation.lhs - equation.rhs
    numerator, denominator = residual.as_numer_denom()
    if denominator.has(variable):
        raise CanvasMathParseError("Variables in denominators are outside the canvas-review scope.")
    try:
        polynomial: Poly = Poly(numerator, variable)
    except PolynomialError as error:
        raise CanvasMathParseError("The equation is not polynomial.") from error
    if polynomial.degree() > 1:
        raise CanvasMathParseError("Only linear equations are supported.")


def _solution_set(equation: Equality, variable: Symbol) -> Set:
    try:
        solutions: Set = solveset(equation, variable, domain=S.Reals)
    except (NotImplementedError, ValueError) as error:
        raise CanvasMathParseError("The equation could not be solved exactly.") from error
    if solutions.has(S.NaN):
        raise CanvasMathParseError("The equation produced an undefined solution.")
    return solutions


def _validate_expected_answer(
    correct_answer: str,
    variable: Symbol,
    expected_solutions: Set,
    max_characters: int,
) -> None:
    answer_equation: Equality = _parse_step_equation(correct_answer, variable, max_characters)
    if _solution_set(answer_equation, variable) != expected_solutions:
        raise CanvasMathParseError("The configured answer does not match the question.")


def _mistake_review(
    index: int,
    region: CanvasTextRegion,
    previous_equation: Equality,
    current_equation: Equality,
    variable: Symbol,
    correct_answer: str,
    current_phase: LearningPhase,
    canvas_regions: list[CanvasTextRegion],
    config: CanvasReviewConfig,
    confidence: float,
) -> CanvasMathReview:
    target_span, replacement_text = _correction_for_additive_inverse(
        region.text,
        previous_equation,
        current_equation,
        variable,
    )
    error_type: ErrorType = _classify_transition(previous_equation, current_equation, variable)
    if target_span is not None and replacement_text is not None:
        error_type = _error_type_for_correction(
            region.text[target_span[0] : target_span[1]],
            replacement_text,
        )
    message: str = getattr(config.messages, error_type)
    if target_span is None and error_type in {"ARITHMETIC_ERROR", "SIGN_ERROR"}:
        numeric_match: re.Match[str] | None = _ISOLATED_NUMERIC_VALUE.search(region.text)
        if numeric_match is not None:
            target_span = numeric_match.span(1)
    if replacement_text is not None:
        corrected_text: str = _replace_span(region.text, target_span, replacement_text)
        if _FINAL_ANSWER.fullmatch(normalize_canvas_math_text(corrected_text)) is not None:
            replacement_text = None

    step_id: str = region.step_id or f"step-{index + 1}"
    classification: CanvasMistakeClassification = CanvasMistakeClassification(
        status="mistake_found",
        mistake_step_id=step_id,
        target_text=(region.text[target_span[0] : target_span[1]] if target_span is not None else region.text),
        target_span=list(target_span) if target_span is not None else None,
        replacement_text=replacement_text,
        confidence=confidence,
    )
    feedback_enabled: bool = current_phase in config.feedback_enabled_phases
    annotation_enabled: bool = current_phase in config.annotation_enabled_phases
    return CanvasMathReview(
        error_type=error_type,
        tutor_feedback=message if feedback_enabled else None,
        canvas_feedback=(
            _mistake_step_feedback(index, canvas_regions, error_type, message, config)
            if feedback_enabled
            else CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None)
        ),
        mistake_classification=classification,
        annotation_intents=(
            _annotation_intents(classification, region, correct_answer)
            if annotation_enabled
            else []
        ),
    )


def _classify_transition(
    previous: Equality,
    current: Equality,
    variable: Symbol,
) -> ErrorType:
    previous_solution: Set = _solution_set(previous, variable)
    current_solution: Set = _solution_set(current, variable)
    if _single_solution(current_solution) == -_single_solution(previous_solution):
        return "SIGN_ERROR"
    if _has_wrong_inverse_operation(previous, current, variable):
        return "OPPOSITE_OPERATION_ERROR"
    if _has_isolated_variable(previous, variable) and _has_isolated_variable(current, variable):
        return "ARITHMETIC_ERROR"
    if _variable_coefficient(previous, variable) not in {None, -1, 0, 1}:
        return "CONCEPTUAL_MISUNDERSTANDING"
    return "PROCEDURAL_ERROR"


def _single_solution(solutions: Set) -> Expr:
    if not getattr(solutions, "is_FiniteSet", False) or len(solutions) != 1:
        return S.NaN
    return next(iter(solutions))


def _has_isolated_variable(equation: Equality, variable: Symbol) -> bool:
    return equation.lhs == variable or equation.rhs == variable


def _variable_coefficient(equation: Equality, variable: Symbol) -> Expr | None:
    variable_side: Expr | None = _variable_side(equation, variable)
    if variable_side is None:
        return None
    try:
        return Poly(variable_side, variable).coeff_monomial(variable)
    except PolynomialError:
        return None


def _variable_side(equation: Equality, variable: Symbol) -> Expr | None:
    if equation.lhs.has(variable) and not equation.rhs.has(variable):
        return equation.lhs
    if equation.rhs.has(variable) and not equation.lhs.has(variable):
        return equation.rhs
    return None


def _has_wrong_inverse_operation(previous: Equality, current: Equality, variable: Symbol) -> bool:
    variable_side: Expr | None = _variable_side(previous, variable)
    if variable_side is None or not _has_isolated_variable(current, variable):
        return False
    try:
        polynomial: Poly = Poly(variable_side, variable)
    except PolynomialError:
        return False
    constant: Expr = polynomial.coeff_monomial(1)
    return constant != 0


def _correction_for_additive_inverse(
    original_text: str,
    previous: Equality,
    current: Equality,
    variable: Symbol,
) -> tuple[tuple[int, int] | None, str | None]:
    variable_side: Expr | None = _variable_side(previous, variable)
    if variable_side is None or not _has_isolated_variable(current, variable):
        return None, None
    try:
        polynomial: Poly = Poly(variable_side, variable)
    except PolynomialError:
        return None, None
    coefficient: Expr = polynomial.coeff_monomial(variable)
    constant: Expr = polynomial.coeff_monomial(1)
    if coefficient != 1 or constant == 0 or constant.is_number is not True:
        return None, None

    span_safe_text: str = original_text.translate(str.maketrans({"−": "-", "–": "-", "—": "-"}))
    match: re.Match[str] | None = _BINARY_NUMERIC_OPERATION.search(span_safe_text)
    if match is None:
        return None, None
    expected_operator: str = "-" if constant > 0 else "+"
    expected_operand: str = str(abs(constant))
    operator: str = match.group(1)
    operand: str = match.group(2)
    if operator != expected_operator and Rational(operand) != abs(constant):
        return (match.start(1), match.end(2)), f"{expected_operator}{expected_operand}"
    if operator != expected_operator:
        return match.span(1), expected_operator
    if Rational(operand) != abs(constant):
        return match.span(2), expected_operand
    return None, None


def _replace_span(text: str, span: tuple[int, int] | None, replacement: str) -> str:
    if span is None:
        return text
    return f"{text[:span[0]]}{replacement}{text[span[1]:]}"


def _error_type_for_correction(target_text: str, replacement_text: str) -> ErrorType:
    target: str = target_text.strip()
    replacement: str = replacement_text.strip()
    if target.startswith(("+", "-")) and replacement.startswith(("+", "-")):
        if target[0] != replacement[0]:
            return "OPPOSITE_OPERATION_ERROR"
    return "ARITHMETIC_ERROR"


def _annotation_intents(
    classification: CanvasMistakeClassification,
    region: CanvasTextRegion,
    correct_answer: str,
) -> list[CanvasAnnotationIntent]:
    if classification.mistake_step_id is None:
        return []
    intents: list[CanvasAnnotationIntent] = [
        CanvasAnnotationIntent(
            kind="circle_target",
            target_step_id=classification.mistake_step_id,
            text=None,
            placement=None,
        )
    ]
    if classification.target_span is None or classification.replacement_text is None:
        return intents
    span: tuple[int, int] = (classification.target_span[0], classification.target_span[1])
    correction: str = _replace_span(region.text, span, classification.replacement_text)
    if normalize_canvas_math_text(correction) == normalize_canvas_math_text(correct_answer):
        return intents
    intents.extend(
        [
            CanvasAnnotationIntent(
                kind="write_correction",
                target_step_id=classification.mistake_step_id,
                text=correction,
                placement="right",
            ),
            CanvasAnnotationIntent(
                kind="draw_arrow",
                target_step_id=classification.mistake_step_id,
                text=None,
                placement=None,
            ),
        ]
    )
    return intents


def _mistake_step_feedback(
    mistake_index: int,
    regions: list[CanvasTextRegion],
    error_type: ErrorType,
    message: str,
    config: CanvasReviewConfig,
) -> CanvasFeedback:
    steps: list[CanvasStepFeedback] = []
    for index, _region in enumerate(regions):
        if index < mistake_index:
            steps.append(
                CanvasStepFeedback(
                    step_number=index + 1,
                    evaluation="CORRECT",
                    error_type=None,
                    feedback=None,
                )
            )
            continue
        steps.append(
            CanvasStepFeedback(
                step_number=index + 1,
                evaluation="INCORRECT",
                error_type=error_type if index == mistake_index else None,
                feedback=message if index == mistake_index else config.messages.downstream_step,
            )
        )
    return CanvasFeedback(
        has_feedback=True,
        step_feedback=steps,
        highlight_instruction=HighlightInstruction(
            step_number=mistake_index + 1,
            highlight_type="ERROR",
            colour="RED",
        ),
    )


def _correct_step_feedback(
    regions: list[CanvasTextRegion],
    phase: LearningPhase,
    config: CanvasReviewConfig,
) -> CanvasFeedback:
    if phase not in config.feedback_enabled_phases:
        return CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None)
    return CanvasFeedback(
        has_feedback=True,
        step_feedback=[
            CanvasStepFeedback(
                step_number=index + 1,
                evaluation="CORRECT",
                error_type=None,
                feedback=None,
            )
            for index, _region in enumerate(regions)
        ],
        highlight_instruction=None,
    )


def _uncertain_review(confidence: float) -> CanvasMathReview:
    return CanvasMathReview(
        error_type=None,
        tutor_feedback=None,
        canvas_feedback=CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None),
        mistake_classification=CanvasMistakeClassification(
            status="uncertain",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=confidence,
        ),
        annotation_intents=[],
    )
