import re
import logging
from pathlib import Path

import yaml

logger = logging.getLogger("ingestion.guardrail")

_rules_path = Path(__file__).parent / "sanya_guardrail" / "classifier_rules.yaml"
_rules_cache = None

def _load_rules() -> dict:
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache

    if not _rules_path.exists():
        logger.warning(f"classifier_rules.yaml not found at {_rules_path} — guardrail checks disabled")
        return {}

    with open(_rules_path) as f:
        _rules_cache = yaml.safe_load(f)

    logger.info("Loaded Sanya's classifier_rules.yaml for guardrail checks")
    return _rules_cache

def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())

def _contains_any(value: str, phrases: list[str]) -> bool:
    return any(phrase in value for phrase in phrases)

def _extract_last_number(value: str) -> float | None:
    matches = re.findall(r"-?\d+(?:\.\d+)?", value)
    if not matches:
        return None
    return float(matches[-1])

def _format_number_for_matching(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)

def contains_answer_reveal(message: str, correct_answer: str, rules: dict) -> bool:
    reveal_config = rules.get("answer_reveal_guardrail", {})
    reveal_phrases = reveal_config.get("reveal_phrases", [])

    normalized_message = _normalize_text(message)
    normalized_answer = _normalize_text(correct_answer)
    correct_value = _extract_last_number(correct_answer)

    if normalized_answer and normalized_answer in normalized_message:
        return True

    if _contains_any(normalized_message, reveal_phrases):
        return True

    if correct_value is None:
        return False

    correct_number = _format_number_for_matching(correct_value)
    return re.search(rf"(?<![\d.])-?{re.escape(correct_number)}(?![\d.])", normalized_message) is not None

def check_safety_terms(text: str, rules: dict) -> tuple[bool, str | None]:
    safety_config = rules.get("safety", {})
    unsafe_terms = safety_config.get("unsafe_terms", [])

    normalized = _normalize_text(text)
    if _contains_any(normalized, unsafe_terms):
        flag_type = safety_config.get("flag_type", "UNSAFE_CONTENT")
        return False, f"Contains unsafe term (flag: {flag_type})"

    return True, None

TYPES_TO_CHECK_REVEAL = {"HINT", "SCAFFOLD_STEP"}

def check_content_item(
    content_id: str,
    content_type: str,
    text: str,
    voice_text: str | None,
    expected_answer: str | None,
    related_answers: list[str] | None = None,
) -> tuple[bool, str | None]:
    rules = _load_rules()
    if not rules:
        logger.debug(f"No rules loaded — skipping guardrail for {content_id}")
        return True, None

    safe, reason = check_safety_terms(text, rules)
    if not safe:
        return False, reason

    if voice_text:
        safe, reason = check_safety_terms(voice_text, rules)
        if not safe:
            return False, f"voice_text: {reason}"

    if content_type in TYPES_TO_CHECK_REVEAL:
        answers_to_check = []
        if expected_answer:
            answers_to_check.append(expected_answer)
        if related_answers:
            answers_to_check.extend(related_answers)

        for answer in answers_to_check:
            if contains_answer_reveal(text, answer, rules):
                return False, f"Text reveals answer '{answer}' (violation: DIRECT_ANSWER_REVEALED)"
            if voice_text and contains_answer_reveal(voice_text, answer, rules):
                return False, f"Voice text reveals answer '{answer}' (violation: DIRECT_ANSWER_REVEALED)"

    return True, None
