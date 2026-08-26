"""Reusable semantic token-difference localization for Canvas math evidence."""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Literal

from app.models.adapters import SpatialMathToken
from app.services.canvas_spatial import canonical_math_token_text


LocalizationLevel = Literal["TOKEN", "SPAN", "STEP"]

_TOKEN_PATTERN = re.compile(r"\d+(?:\.\d*)?|\.\d+|[A-Za-z]+|[√()+\-*/=]")
_SUPERSCRIPT_DIGITS = str.maketrans(
    "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "0123456789",
)
_LATEX_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\times", "*"),
    (r"\cdot", "*"),
    (r"\div", "/"),
    (r"\sqrt", "√"),
    (r"\left", ""),
    (r"\right", ""),
)


@dataclass(frozen=True)
class _ComparableToken:
    text: str
    raw_text: str
    token_id: str | None
    semantic_path: str | None
    alignment_confidence: float
    has_geometry: bool


@dataclass(frozen=True)
class MathLocalization:
    """Semantic difference and its best available submitted-token target."""

    target_token_ids: tuple[str, ...]
    actual_text: str
    expected_text: str
    target_span: tuple[int, int] | None
    semantic_path: str | None
    localization_level: LocalizationLevel
    fallback_reason: str | None


def localize_math_difference(
    expected_text: str,
    actual_text: str,
    actual_tokens: list[SpatialMathToken],
) -> MathLocalization | None:
    """Return the smallest unambiguous submitted-token difference, if any."""

    expected_tokens = _tokenize(expected_text)
    comparable_actual = [
        _ComparableToken(
            text=_normalise(token.text),
            raw_text=token.text,
            token_id=token.token_id,
            semantic_path=token.semantic_path or None,
            alignment_confidence=token.alignment_confidence,
            has_geometry=bool(token.bounding_box),
        )
        for token in actual_tokens
        if _normalise(token.text) != "^"
    ]
    if not expected_tokens or not comparable_actual:
        return _step_fallback("MISSING_TOKEN_EVIDENCE")

    opcodes = [
        opcode
        for opcode in SequenceMatcher(
            a=[token.text for token in expected_tokens],
            b=[token.text for token in comparable_actual],
            autojunk=False,
        ).get_opcodes()
        if opcode[0] != "equal"
    ]
    if not opcodes:
        return None
    if len(opcodes) != 1:
        return _step_fallback("MULTIPLE_SEMANTIC_DIFFERENCES")

    tag, expected_start, expected_end, actual_start, actual_end = opcodes[0]
    if tag == "insert" or actual_start == actual_end:
        return _step_fallback("MISSING_EXPECTED_TOKEN")

    target_tokens = comparable_actual[actual_start:actual_end]
    target_ids = tuple(
        token.token_id for token in target_tokens if token.token_id is not None
    )
    if len(target_ids) != len(target_tokens):
        return _step_fallback("TOKEN_ID_UNAVAILABLE")

    expected_segment = expected_tokens[expected_start:expected_end]
    actual_segment = "".join(token.raw_text for token in target_tokens)
    expected_segment_text = "".join(token.text for token in expected_segment)
    target_span = _target_span(actual_text, comparable_actual, actual_start, actual_end)
    level: LocalizationLevel = "TOKEN" if len(target_tokens) == 1 else "SPAN"
    semantic_path: str | None = (
        target_tokens[0].semantic_path if len(target_tokens) == 1 else None
    )
    fallback_reason: str | None = (
        "TOKEN_GEOMETRY_UNAVAILABLE"
        if any(
            token.alignment_confidence < 0.9 or not token.has_geometry
            for token in target_tokens
        )
        else None
    )
    return MathLocalization(
        target_token_ids=target_ids,
        actual_text=actual_segment,
        expected_text=expected_segment_text,
        target_span=target_span,
        semantic_path=semantic_path,
        localization_level=level,
        fallback_reason=fallback_reason,
    )


def _step_fallback(reason: str) -> MathLocalization:
    return MathLocalization(
        target_token_ids=(),
        actual_text="",
        expected_text="",
        target_span=None,
        semantic_path=None,
        localization_level="STEP",
        fallback_reason=reason,
    )


def _tokenize(value: str) -> list[_ComparableToken]:
    normalized = _normalise(value)
    return [
        _ComparableToken(
            text=match.group(0),
            raw_text=match.group(0),
            token_id=None,
            semantic_path=None,
            alignment_confidence=1.0,
            has_geometry=False,
        )
        for match in _TOKEN_PATTERN.finditer(normalized)
        if match.group(0) != "^"
    ]


def _normalise(value: str) -> str:
    normalized = value
    for source, replacement in _LATEX_REPLACEMENTS:
        normalized = normalized.replace(source, replacement)
    normalized = re.sub(
        r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r"\1/\2",
        normalized,
    )
    normalized = normalized.translate(_SUPERSCRIPT_DIGITS)
    normalized = canonical_math_token_text(normalized)
    return normalized


def _target_span(
    actual_text: str,
    actual_tokens: list[_ComparableToken],
    start: int,
    end: int,
) -> tuple[int, int] | None:
    normalized_chars: list[str] = []
    raw_indices: list[int] = []
    for raw_index, character in enumerate(actual_text):
        normalized_character = _normalise(character)
        for normalized_value in normalized_character:
            normalized_chars.append(normalized_value)
            raw_indices.append(raw_index)

    normalized_text = "".join(normalized_chars)
    cursor = 0
    spans: list[tuple[int, int]] = []
    for token in actual_tokens:
        token_text = token.text
        position = normalized_text.find(token_text, cursor)
        if position < 0 or not token_text:
            return None
        spans.append((raw_indices[position], raw_indices[position + len(token_text) - 1] + 1))
        cursor = position + len(token_text)
    if start < 0 or end > len(spans) or start >= end:
        return None
    return min(span[0] for span in spans[start:end]), max(span[1] for span in spans[start:end])
