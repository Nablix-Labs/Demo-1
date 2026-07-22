from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.ai_engine.classifier import contains_answer_reveal
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.ai_engine.openai_client import OpenAIAIEngineClient
from app.ai_engine.schemas import ErrorType, StrictSchema
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.session_review import (
    CallToAction,
    GeneratedSessionReview,
    MasteryStatus,
    QuestionAttempt,
    SessionReviewRequest,
    SessionReviewResponse,
)
from app.services.session_service import correct_answer_for


SESSION_REVIEW_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "session_review.yaml"
)
VOICE_DELIVERY_ORDER: list[str] = [
    "category_1_strength",
    "category_2_first_error",
    "category_3_pattern",
    "category_4_next_practice",
    "category_5_mastery",
    "b6_hook",
]


class SessionReviewValidationError(ValueError):
    pass


class QuestionAnswerNotFoundError(SessionReviewValidationError):
    pass


class SessionReviewFallbackConfig(StrictSchema):
    category_1_strength_template: str
    category_2_first_error_template: str
    category_4_next_practice_template: str
    category_5_mastery_by_status: dict[MasteryStatus, str]
    student_facing_summary_template: str
    b6_hook: str


class SessionReviewConfig(StrictSchema):
    generation_instructions: str
    stricter_guardrail_instruction: str
    error_labels: dict[ErrorType, str]
    possible_pattern_template: str
    confirmed_pattern_template: str
    forbidden_output_phrases: list[str]
    practice_focus_by_error: dict[ErrorType, str]
    default_practice_focus: str
    fallback: SessionReviewFallbackConfig


@dataclass(frozen=True)
class ReviewEvidence:
    concept: str
    total_attempts: int
    correct_attempts: int
    hints_used: int
    independent_correct: int
    strengths: list[str]
    first_error_description: str | None
    independent_later_error_description: str | None
    dominant_error: ErrorType | None
    dominant_error_count: int
    pattern_confirmed: bool
    mastery_status: str
    hint_dependency_score: float
    recommended_entry_phase: str
    next_practice_focus: str


@lru_cache(maxsize=1)
def load_session_review_config() -> SessionReviewConfig:
    raw_config: object = yaml.safe_load(
        SESSION_REVIEW_CONFIG_PATH.read_text(encoding="utf-8")
    )
    return SessionReviewConfig.model_validate(raw_config)


def validate_question_order(history: list[QuestionAttempt]) -> None:
    latest_attempt_by_question: dict[str, int] = {}
    for attempt in history:
        previous_attempt: int = latest_attempt_by_question.get(attempt.question_id, 0)
        if attempt.attempt_number <= previous_attempt:
            raise SessionReviewValidationError(
                "per_question_history must be chronological with increasing attempt numbers"
            )
        latest_attempt_by_question[attempt.question_id] = attempt.attempt_number


def validate_session_history(request: SessionReviewRequest) -> None:
    history: list[QuestionAttempt] = request.session_summary.per_question_history
    validate_question_order(history)
    expected_attempts: int = request.session_summary.session_performance.total_attempts
    if len(history) != expected_attempts:
        raise SessionReviewValidationError(
            "per_question_history length must match session_performance.total_attempts"
        )
    question_ids: set[str] = {attempt.question_id for attempt in history}
    if any(
        feedback.question_id not in question_ids
        for feedback in request.session_summary.canvas_feedback_history
    ):
        raise SessionReviewValidationError(
            "canvas feedback must reference a question in per_question_history"
        )


def resolve_protected_answers(history: list[QuestionAttempt]) -> list[str]:
    answers: list[str] = []
    for question_id in dict.fromkeys(attempt.question_id for attempt in history):
        answer: str | None = correct_answer_for(question_id)
        if answer is None:
            raise QuestionAnswerNotFoundError(
                f"No correct answer is registered for question_id={question_id}"
            )
        answers.append(answer)
    return answers


def select_strengths(history: list[QuestionAttempt]) -> list[str]:
    return list(
        dict.fromkeys(
            description
            for attempt in history
            for description in attempt.successful_step_descriptions
        )
    )


def select_first_error(history: list[QuestionAttempt]) -> QuestionAttempt | None:
    return next(
        (
            attempt
            for attempt in history
            if attempt.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
        ),
        None,
    )


def select_independent_later_error(
    history: list[QuestionAttempt],
    first_error: QuestionAttempt | None,
) -> QuestionAttempt | None:
    if first_error is None:
        return None
    first_error_index: int = history.index(first_error)
    return next(
        (
            attempt
            for attempt in history[first_error_index + 1 :]
            if attempt.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
            and attempt.question_id != first_error.question_id
            and attempt.error_type != first_error.error_type
        ),
        None,
    )


def build_review_evidence(
    request: SessionReviewRequest,
    config: SessionReviewConfig,
) -> ReviewEvidence:
    history: list[QuestionAttempt] = request.session_summary.per_question_history
    strengths: list[str] = select_strengths(history)
    if len(strengths) == 0:
        raise SessionReviewValidationError(
            "per_question_history must contain at least one successful step description"
        )

    first_error: QuestionAttempt | None = select_first_error(history)
    later_error: QuestionAttempt | None = select_independent_later_error(history, first_error)
    dominant_error: ErrorType | None = request.student_model.dominant_error_type
    dominant_error_count: int = (
        request.student_model.error_counts.get(dominant_error, 0)
        if dominant_error is not None
        else 0
    )
    next_practice_focus: str = config.default_practice_focus
    if dominant_error is not None:
        next_practice_focus = config.practice_focus_by_error.get(
            dominant_error,
            config.default_practice_focus,
        )

    return ReviewEvidence(
        concept=request.session_summary.concept_id,
        total_attempts=request.session_summary.session_performance.total_attempts,
        correct_attempts=request.session_summary.session_performance.correct_attempts,
        hints_used=request.session_summary.session_performance.hints_used,
        independent_correct=sum(1 for attempt in history if attempt.independent_success),
        strengths=strengths,
        first_error_description=(first_error.error_description if first_error is not None else None),
        independent_later_error_description=(
            later_error.error_description if later_error is not None else None
        ),
        dominant_error=dominant_error,
        dominant_error_count=dominant_error_count,
        pattern_confirmed=request.student_model.error_confirmed_pattern,
        mastery_status=request.student_model.mastery_status,
        hint_dependency_score=request.student_model.hint_dependency_score,
        recommended_entry_phase=request.student_model.recommended_entry_phase,
        next_practice_focus=next_practice_focus,
    )


def build_openai_review_context(
    evidence: ReviewEvidence,
    config: SessionReviewConfig,
) -> dict[str, object]:
    return {
        "review_instructions": config.generation_instructions,
        "concept": evidence.concept,
        "performance": {
            "total_attempts": evidence.total_attempts,
            "correct_attempts": evidence.correct_attempts,
            "hints_used": evidence.hints_used,
            "independent_correct": evidence.independent_correct,
        },
        "strengths": evidence.strengths,
        "first_error_description": evidence.first_error_description,
        "independent_later_error_description": evidence.independent_later_error_description,
        "pattern": {
            "dominant_error": evidence.dominant_error,
            "occurrence_count": evidence.dominant_error_count,
            "confirmed": evidence.pattern_confirmed,
        },
        "mastery": {
            "status": evidence.mastery_status,
            "hint_dependency_score": evidence.hint_dependency_score,
            "recommended_entry_phase": evidence.recommended_entry_phase,
        },
        "next_practice_focus": evidence.next_practice_focus,
    }


def review_text(review: GeneratedSessionReview) -> str:
    categories = review.five_category_summary
    return " ".join(
        text
        for text in (
            categories.category_1_strength,
            categories.category_2_first_error,
            categories.category_3_pattern,
            categories.category_4_next_practice,
            categories.category_5_mastery,
            review.student_facing_summary,
            review.b6_hook,
        )
        if text is not None
    )


def validate_review_language(
    review: GeneratedSessionReview,
    config: SessionReviewConfig,
) -> None:
    normalized_review: str = review_text(review).lower()
    forbidden_phrase: str | None = next(
        (
            phrase
            for phrase in config.forbidden_output_phrases
            if phrase.lower() in normalized_review
        ),
        None,
    )
    if forbidden_phrase is not None:
        raise ValueError(
            f"Generated session review contains forbidden phrase: {forbidden_phrase}"
        )


def review_contains_answer(
    review: GeneratedSessionReview,
    protected_answers: list[str],
    rules: ClassifierRulesConfig,
) -> bool:
    generated_text: str = review_text(review)
    return any(
        contains_answer_reveal(generated_text, answer, rules)
        for answer in protected_answers
    )


def validate_evidence_does_not_reveal_answers(
    evidence: ReviewEvidence,
    protected_answers: list[str],
    rules: ClassifierRulesConfig,
) -> None:
    evidence_text: str = " ".join(
        [
            *evidence.strengths,
            evidence.first_error_description or "",
            evidence.independent_later_error_description or "",
            evidence.next_practice_focus,
        ]
    )
    if any(
        contains_answer_reveal(evidence_text, answer, rules)
        for answer in protected_answers
    ):
        raise SessionReviewValidationError(
            "session review evidence must not contain a protected answer"
        )


def apply_deterministic_review_rules(
    generated: GeneratedSessionReview,
    request: SessionReviewRequest,
    config: SessionReviewConfig,
) -> GeneratedSessionReview:
    error_count: int = sum(request.student_model.error_counts.values())
    dominant_error: ErrorType | None = request.student_model.dominant_error_type
    dominant_count: int = (
        request.student_model.error_counts.get(dominant_error, 0)
        if dominant_error is not None
        else 0
    )
    pattern_text: str | None = None
    if dominant_error is not None and request.student_model.error_confirmed_pattern:
        pattern_text = config.confirmed_pattern_template.format(
            error_label=config.error_labels[dominant_error]
        )
    elif dominant_error is not None and dominant_count >= 3:
        pattern_text = config.possible_pattern_template.format(
            error_label=config.error_labels[dominant_error]
        )

    categories = generated.five_category_summary.model_copy(
        update={
            "category_2_first_error": (
                generated.five_category_summary.category_2_first_error
                if error_count > 0
                else None
            ),
            "category_3_pattern": pattern_text,
        }
    )
    suppress_hook: bool = (
        request.session_summary.session_performance.rescue_mode_activations > 0
        or request.session_summary.session_performance.long_pressure_events > 0
    )
    return generated.model_copy(
        update={
            "five_category_summary": categories,
            "b6_hook": None if suppress_hook else generated.b6_hook,
        }
    )


def select_call_to_action(request: SessionReviewRequest) -> CallToAction:
    performance = request.session_summary.session_performance
    if performance.rescue_mode_activations > 0 or performance.long_pressure_events > 0:
        return "NONE"
    if request.student_model.mastery_status == "MASTERED":
        return "NEXT_TOPIC"
    return "CONTINUE_PRACTICE"


def build_fallback_review(
    evidence: ReviewEvidence,
    config: SessionReviewConfig,
) -> GeneratedSessionReview:
    fallback = config.fallback
    category_2_first_error: str | None = None
    if evidence.first_error_description is not None:
        category_2_first_error = fallback.category_2_first_error_template.format(
            error_description=evidence.first_error_description
        )
    return GeneratedSessionReview.model_validate(
        {
            "five_category_summary": {
                "category_1_strength": fallback.category_1_strength_template.format(
                    strength=evidence.strengths[0]
                ),
                "category_2_first_error": category_2_first_error,
                "category_3_pattern": None,
                "category_4_next_practice": fallback.category_4_next_practice_template.format(
                    practice_focus=evidence.next_practice_focus
                ),
                "category_5_mastery": fallback.category_5_mastery_by_status[
                    evidence.mastery_status
                ],
            },
            "student_facing_summary": fallback.student_facing_summary_template.format(
                practice_focus=evidence.next_practice_focus
            ),
            "b6_hook": fallback.b6_hook,
        }
    )


def build_openai_session_review_client(settings: Settings) -> OpenAIAIEngineClient | None:
    if settings.use_openai_ai_engine is False or settings.openai_api_key == "":
        return None
    return OpenAIAIEngineClient(
        api_key=settings.openai_api_key,
        model=settings.openai_ai_engine_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        prompt_cache_key_enabled=settings.openai_prompt_cache_key_enabled,
        retry_count=settings.adapter_request_retry_count,
    )


def generate_session_review(request: SessionReviewRequest) -> SessionReviewResponse:
    validate_session_history(request)
    protected_answers: list[str] = resolve_protected_answers(
        request.session_summary.per_question_history
    )
    config: SessionReviewConfig = load_session_review_config()
    evidence: ReviewEvidence = build_review_evidence(request, config)
    rules: ClassifierRulesConfig = load_classifier_rules()
    validate_evidence_does_not_reveal_answers(evidence, protected_answers, rules)
    context: dict[str, object] = build_openai_review_context(evidence, config)
    client: OpenAIAIEngineClient | None = build_openai_session_review_client(get_settings())
    generated: GeneratedSessionReview
    fallback_reason: str | None = None
    guardrail_retry: bool = False

    if client is None:
        fallback_reason = "openai_not_configured"
        generated = build_fallback_review(evidence, config)
    else:
        try:
            generated = GeneratedSessionReview.model_validate(
                client.generate_session_review(
                    context=context,
                    schema=GeneratedSessionReview.model_json_schema(),
                )
            )
            generated = apply_deterministic_review_rules(generated, request, config)
            validate_review_language(generated, config)
            if review_contains_answer(generated, protected_answers, rules):
                guardrail_retry = True
                generated = GeneratedSessionReview.model_validate(
                    client.regenerate_session_review(
                        context=context,
                        schema=GeneratedSessionReview.model_json_schema(),
                        stricter_instruction=config.stricter_guardrail_instruction,
                    )
                )
                generated = apply_deterministic_review_rules(generated, request, config)
                validate_review_language(generated, config)
                if review_contains_answer(generated, protected_answers, rules):
                    fallback_reason = "guardrail_failed_twice"
                    generated = build_fallback_review(evidence, config)
        except (AdapterError, ValidationError, ValueError) as error:
            fallback_reason = type(error).__name__
            generated = build_fallback_review(evidence, config)

    generated = apply_deterministic_review_rules(generated, request, config)
    validate_review_language(generated, config)
    if review_contains_answer(generated, protected_answers, rules):
        raise RuntimeError("Configured session review fallback reveals a protected answer")

    # Null categories are skipped in the spoken delivery, per the contract example.
    category_values: dict[str, str | None] = {
        **generated.five_category_summary.model_dump(),
        "b6_hook": generated.b6_hook,
    }
    response = SessionReviewResponse(
        **generated.model_dump(),
        call_to_action=select_call_to_action(request),
        voice_delivery_order=[
            key for key in VOICE_DELIVERY_ORDER if category_values.get(key) is not None
        ],
        answer_reveal_allowed=False,
        guardrail_passed=True,
    )
    logger.info(
        "session_review_generated",
        extra={
            "provider": "openai",
            "model": get_settings().openai_ai_engine_model,
            "guardrail_retry": guardrail_retry,
            "fallback_reason": fallback_reason,
            "category_2_is_null": response.five_category_summary.category_2_first_error is None,
            "category_3_is_null": response.five_category_summary.category_3_pattern is None,
            "b6_hook_is_null": response.b6_hook is None,
            "call_to_action": response.call_to_action,
        },
    )
    return response
