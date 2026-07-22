from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import Field

from app.ai_engine.canvas_math_review import review_canvas_math
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.ai_engine.schemas import (
    CanvasAnnotationIntent,
    CanvasFeedback,
    CanvasMathReview,
    CanvasMistakeClassification,
    CanvasTextRegion,
    ErrorType,
    EvaluationCategory,
    GuardrailCheck,
    HintLevel,
    InputSource,
    IntentType,
    LearningEventType,
    LearningPhase,
    ResponseStrategy,
    SafetyCheck,
    StrictSchema,
    StudentModelEvent,
    TutorResponse,
    VisualCue,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import ConversationAction, ConversationMessage, ConversationState

if TYPE_CHECKING:
    from app.ai_engine.openai_client import (
        OpenAIAIEngineClient,
        OpenAITutorMessage,
        OpenAITutorTurn,
    )


class ClassificationRequest(StrictSchema):
    question: str
    correct_answer: str
    student_input: str
    current_phase: LearningPhase
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    question_completed: bool = False
    question_number: int = Field(default=1, ge=1)
    current_hint_level: HintLevel | None
    concept_id: str | None = None
    difficulty: str = "FOUNDATION"
    max_hint_results: int = Field(default=3, ge=1)
    exclude_content_ids: list[str] = Field(default_factory=list)
    canvas_regions: list[CanvasTextRegion] = Field(default_factory=list)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    conversation_state: ConversationState | None = None


@dataclass(frozen=True)
class TutorDecision:
    intent: IntentType
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    response_strategy: ResponseStrategy
    hint_level: HintLevel | None
    canvas_review: CanvasMathReview | None


def classify_student_response(request: ClassificationRequest) -> TutorResponse:
    rules: ClassifierRulesConfig = load_classifier_rules()
    settings: Settings = get_settings()
    openai_client: OpenAIAIEngineClient | None = build_openai_ai_engine_client(settings)
    safety_check: SafetyCheck = check_student_message_safety(request.student_input, rules)
    intent: IntentType = detect_student_intent(request.student_input, rules)

    if safety_check.passed is False:
        safety_decision = TutorDecision(
            intent=intent,
            evaluation=None,
            error_type=None,
            response_strategy="SAFETY_RESPONSE",
            hint_level=None,
            canvas_review=None,
        )
        return build_tutor_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            decision=safety_decision,
            answer_reveal_allowed=False,
            confidence=rules.confidence.safety_response,
            tutor_message_override=None,
            voice_message_override=None,
        )

    if is_contextual_acknowledgement(request, rules):
        return build_contextual_acknowledgement_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
        )

    evaluation: EvaluationCategory | None = evaluate_answer_attempt(request, intent, rules)
    error_type: ErrorType | None = classify_student_error(request, evaluation, rules)
    response_strategy: ResponseStrategy = select_response_strategy(
        intent=intent,
        evaluation=evaluation,
        current_phase=request.current_phase,
        attempt_count=request.attempt_count,
        rules=rules,
    )
    hint_level: HintLevel | None = select_hint_level(
        response_strategy=response_strategy,
        current_hint_level=request.current_hint_level,
        attempt_count=request.attempt_count,
    )
    deterministic_decision = build_tutor_decision(
        request=request,
        rules=rules,
        intent=intent,
        evaluation=evaluation,
        error_type=error_type,
        response_strategy=response_strategy,
        hint_level=hint_level,
        confidence=rules.confidence.standard_response,
    )
    if request.input_source == "CANVAS":
        canvas_context = build_canvas_wording_context(
            deterministic_decision.canvas_review,
            request.canvas_regions,
        )
        openai_message: OpenAITutorMessage | None = build_tutor_message_with_openai(
            request=request,
            intent=deterministic_decision.intent,
            evaluation=deterministic_decision.evaluation,
            error_type=deterministic_decision.error_type,
            response_strategy=deterministic_decision.response_strategy,
            hint_level=deterministic_decision.hint_level,
            canvas_context=canvas_context,
            openai_client=openai_client,
        )
        return build_tutor_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            decision=deterministic_decision,
            answer_reveal_allowed=False,
            confidence=rules.confidence.standard_response,
            tutor_message_override=(
                openai_message.tutor_message if openai_message is not None else None
            ),
            voice_message_override=(
                openai_message.tutor_message_voice_optimised
                if openai_message is not None
                else None
            ),
        )

    if should_use_deterministic_tutor_turn(request, intent, rules):
        return build_tutor_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            decision=deterministic_decision,
            answer_reveal_allowed=False,
            confidence=rules.confidence.standard_response,
            tutor_message_override=None,
            voice_message_override=None,
        )

    openai_turn: OpenAITutorTurn | None = generate_tutor_turn_with_openai(
        request=request,
        grounded_intent=intent,
        grounded_evaluation=evaluation,
        grounded_error_type=error_type,
        openai_client=openai_client,
    )
    if openai_turn is None:
        return build_tutor_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            decision=deterministic_decision,
            answer_reveal_allowed=False,
            confidence=rules.confidence.standard_response,
            tutor_message_override=None,
            voice_message_override=None,
        )

    decision = build_openai_tutor_decision(request, rules, intent, evaluation, openai_turn)
    return build_tutor_response(
        request=request,
        rules=rules,
        safety_check=safety_check,
        decision=decision,
        answer_reveal_allowed=False,
        confidence=openai_turn.confidence,
        tutor_message_override=openai_turn.tutor_message,
        voice_message_override=openai_turn.tutor_message_voice_optimised,
    )


def build_openai_ai_engine_client(settings: Settings) -> OpenAIAIEngineClient | None:
    if settings.use_openai_ai_engine is False:
        return None
    if settings.openai_api_key == "":
        return None
    from app.ai_engine.openai_client import OpenAIAIEngineClient

    return OpenAIAIEngineClient(
        api_key=settings.openai_api_key,
        model=settings.openai_ai_engine_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        prompt_cache_key_enabled=settings.openai_prompt_cache_key_enabled,
        retry_count=settings.adapter_request_retry_count,
    )


def generate_tutor_turn_with_openai(
    request: ClassificationRequest,
    grounded_intent: IntentType,
    grounded_evaluation: EvaluationCategory | None,
    grounded_error_type: ErrorType | None,
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAITutorTurn | None:
    if openai_client is None:
        return None

    try:
        return openai_client.generate_tutor_turn(
            question=request.question,
            correct_answer=request.correct_answer,
            student_input=request.student_input,
            phase=request.current_phase,
            input_source=request.input_source,
            transcript_confidence=request.transcript_confidence,
            attempt_count=request.attempt_count,
            current_hint_level=request.current_hint_level,
            question_completed=request.question_completed,
            grounded_intent=grounded_intent,
            grounded_evaluation=grounded_evaluation,
            grounded_error_type=grounded_error_type,
            conversation_history=request.conversation_history,
            conversation_state=request.conversation_state,
        )
    except AdapterError as error:
        logger.warning(
            "openai_ai_engine_fallback",
            extra={"step": "tutor_turn", "detail": error.message},
        )
        return None


def should_use_deterministic_tutor_turn(
    request: ClassificationRequest,
    intent: IntentType,
    rules: ClassifierRulesConfig,
) -> bool:
    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE"}:
        return True
    return request.input_source == "VOICE" and is_low_confidence(
        request.transcript_confidence,
        rules,
    )


def build_openai_tutor_decision(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    deterministic_intent: IntentType,
    deterministic_evaluation: EvaluationCategory | None,
    openai_turn: OpenAITutorTurn,
) -> TutorDecision:
    intent = (
        deterministic_intent
        if deterministic_evaluation == "CORRECT"
        else openai_turn.intent
    )
    evaluation = (
        "CORRECT"
        if deterministic_evaluation == "CORRECT"
        else openai_turn.evaluation
    )
    error_type: ErrorType | None = openai_turn.error_type
    if evaluation not in {"INCORRECT", "PARTIALLY_CORRECT"}:
        error_type = None
    elif error_type is None:
        error_type = "UNKNOWN_ERROR"

    response_strategy: ResponseStrategy = select_response_strategy(
        intent=intent,
        evaluation=evaluation,
        current_phase=request.current_phase,
        attempt_count=request.attempt_count,
        rules=rules,
    )
    hint_level: HintLevel | None = select_hint_level(
        response_strategy=response_strategy,
        current_hint_level=request.current_hint_level,
        attempt_count=request.attempt_count,
    )
    if openai_turn.response_strategy != response_strategy or openai_turn.hint_level != hint_level:
        logger.warning(
            "openai_tutor_turn_policy_normalized",
            extra={
                "model_response_strategy": openai_turn.response_strategy,
                "required_response_strategy": response_strategy,
                "model_hint_level": openai_turn.hint_level,
                "required_hint_level": hint_level,
                "phase": request.current_phase,
            },
        )

    return TutorDecision(
        intent=intent,
        evaluation=evaluation,
        error_type=error_type,
        response_strategy=response_strategy,
        hint_level=hint_level,
        canvas_review=None,
    )


def build_tutor_message_with_openai(
    request: ClassificationRequest,
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    hint_level: HintLevel | None,
    canvas_context: dict[str, object] | None,
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAITutorMessage | None:
    if openai_client is None:
        return None
    if evaluation == "CORRECT":
        return None
    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE"}:
        return None
    if request.input_source == "CANVAS" and canvas_context is None:
        return None

    try:
        return openai_client.build_tutor_message(
            question=request.question,
            student_input=request.student_input,
            evaluation=evaluation,
            error_type=error_type,
            response_strategy=response_strategy,
            hint_level=hint_level,
            phase=request.current_phase,
            conversation_history=request.conversation_history,
            canvas_context=canvas_context,
        )
    except AdapterError as error:
        logger.warning(
            "openai_ai_engine_fallback",
            extra={"step": "tutor_message", "detail": error.message},
        )
        return None


def check_student_message_safety(student_input: str, rules: ClassifierRulesConfig) -> SafetyCheck:
    normalized_input: str = normalize_text(student_input)

    if contains_any(normalized_input, rules.safety.unsafe_terms):
        return SafetyCheck(passed=False, flag_type=rules.safety.flag_type, action_taken=rules.safety.action_taken)

    return SafetyCheck(passed=True, flag_type=None, action_taken=None)


def detect_student_intent(student_input: str, rules: ClassifierRulesConfig) -> IntentType:
    normalized_input: str = normalize_text(student_input)

    if detects_override_attempt(normalized_input, rules):
        return "ATTEMPTING_OVERRIDE"
    if detects_direct_answer_request(normalized_input, rules):
        return "REQUESTING_ANSWER"
    for intent, phrases in rules.intent_phrases.items():
        if contains_any(normalized_input, phrases):
            return intent
    if "?" in student_input and not contains_any(normalized_input, rules.answer_patterns.answer_notation):
        return "ASKING_QUESTION"

    return "SUBMITTING_ANSWER"


def evaluate_answer_attempt(
    request: ClassificationRequest,
    intent: IntentType,
    rules: ClassifierRulesConfig,
) -> EvaluationCategory | None:
    normalized_input: str = normalize_answer_input(request, rules)

    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE", "REQUESTING_HINT", "ASKING_QUESTION"}:
        return None
    if request.input_source == "VOICE" and is_low_confidence(request.transcript_confidence, rules):
        return "UNCLEAR"
    if intent == "OFF_TOPIC":
        return "IRRELEVANT"
    if intent == "EXPRESSING_CONFUSION":
        return "NO_ATTEMPT"
    if normalized_input == "" or contains_any(normalized_input, rules.answer_patterns.no_attempt):
        return "NO_ATTEMPT"
    if is_ambiguous_answer(normalized_input, rules):
        return "UNCLEAR"
    if is_voice_value_only_correct(request, rules):
        return "CORRECT"
    if is_value_only_correct(request):
        return "PARTIALLY_CORRECT"
    if is_correct_answer(request, rules):
        return "CORRECT"
    if has_visible_correct_method(normalized_input, rules):
        return "PARTIALLY_CORRECT"

    return "INCORRECT"


def classify_student_error(
    request: ClassificationRequest,
    evaluation: EvaluationCategory | None,
    rules: ClassifierRulesConfig,
) -> ErrorType | None:
    if evaluation not in {"INCORRECT", "PARTIALLY_CORRECT"}:
        return None

    normalized_input: str = normalize_answer_input(request, rules)
    normalized_question: str = normalize_text(request.question)
    student_value: float | None = extract_last_number(normalized_input)
    correct_value: float | None = extract_last_number(request.correct_answer)

    if is_value_only_correct(request):
        return "NOTATION_ISSUE"
    if contains_any(normalized_input, rules.error_patterns.insufficient_information) and not contains_any(
        normalized_input,
        rules.answer_patterns.answer_notation,
    ):
        return "INSUFFICIENT_INFORMATION"
    if contains_any(normalized_input, rules.error_patterns.unknown_error):
        return "UNKNOWN_ERROR"
    if (
        normalized_question == normalize_text(rules.diagnostic_cases.sign_error.question)
        and student_value == rules.diagnostic_cases.sign_error.student_value
        and correct_value == rules.diagnostic_cases.sign_error.correct_value
    ):
        return "SIGN_ERROR"
    if (
        normalized_question == normalize_text(rules.diagnostic_cases.opposite_operation_error.question)
        and student_value == rules.diagnostic_cases.opposite_operation_error.student_value
    ):
        return "OPPOSITE_OPERATION_ERROR"
    if is_addition_opposite_operation_error(request, student_value, correct_value):
        return "OPPOSITE_OPERATION_ERROR"
    if (
        normalized_question == normalize_text(rules.diagnostic_cases.conceptual_misunderstanding.question)
        and student_value == rules.diagnostic_cases.conceptual_misunderstanding.student_value
    ):
        return "CONCEPTUAL_MISUNDERSTANDING"
    if normalized_question == normalize_text(rules.diagnostic_cases.procedural_error.question) and contains_any(
        normalized_input,
        rules.diagnostic_cases.procedural_error.phrases,
    ):
        return "PROCEDURAL_ERROR"
    if has_visible_correct_method(normalized_input, rules):
        return "ARITHMETIC_ERROR"

    return "UNKNOWN_ERROR"


def select_response_strategy(
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    current_phase: LearningPhase,
    attempt_count: int,
    rules: ClassifierRulesConfig,
) -> ResponseStrategy:
    if intent == "ACKNOWLEDGEMENT":
        return "CONTINUE"
    if intent in rules.strategy_rules.clarify_intents:
        return "CLARIFY"
    if intent == rules.strategy_rules.hint_intent:
        return "GUIDED_HINT"
    if current_phase == rules.strategy_rules.diagnostic_phase:
        return "DIAGNOSTIC_PROMPT"
    if current_phase == rules.strategy_rules.concept_orientation_phase:
        return "CONFIRM_CORRECT" if evaluation == "CORRECT" else "CLARIFY"
    if evaluation == "CORRECT":
        return "MASTERY_CONFIRM" if current_phase == rules.strategy_rules.review_phase else "CONFIRM_CORRECT"
    if evaluation in {"INCORRECT", "PARTIALLY_CORRECT"} and current_phase == rules.strategy_rules.guided_practice_phase:
        if attempt_count >= rules.strategy_rules.worked_example_min_attempt_count:
            return "PROVIDE_WORKED_EXAMPLE"
        if attempt_count >= rules.strategy_rules.scaffold_min_attempt_count:
            return "SCAFFOLD"
        return "GUIDED_HINT"
    if (
        evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
        and current_phase == rules.strategy_rules.independent_practice_phase
    ):
        return "ENCOURAGE_RETRY"
    if evaluation in {"INCORRECT", "PARTIALLY_CORRECT"} and current_phase == rules.strategy_rules.review_phase:
        return "GUIDED_HINT"

    return "CLARIFY"


def select_hint_level(
    response_strategy: ResponseStrategy,
    current_hint_level: HintLevel | None,
    attempt_count: int,
) -> HintLevel | None:
    if response_strategy != "GUIDED_HINT":
        return None
    if current_hint_level is None:
        if attempt_count <= 1:
            return 1
        if attempt_count == 2:
            return 2
        return 3
    if current_hint_level == 1:
        return 2
    return 3


def build_tutor_decision(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    hint_level: HintLevel | None,
    confidence: float,
) -> TutorDecision:
    canvas_review: CanvasMathReview | None = None
    if request.input_source == "CANVAS" and intent == "SUBMITTING_ANSWER":
        canvas_review = review_canvas_math(
            question=request.question,
            correct_answer=request.correct_answer,
            current_phase=request.current_phase,
            canvas_regions=request.canvas_regions,
            config=rules.canvas_review,
            confidence=confidence,
        )

    effective_error_type: ErrorType | None = (
        canvas_review.error_type
        if canvas_review is not None and canvas_review.error_type is not None
        else error_type
    )
    canvas_mistake_found: bool = (
        canvas_review is not None
        and canvas_review.mistake_classification.status == "mistake_found"
    )
    effective_evaluation: EvaluationCategory | None = evaluation
    if canvas_mistake_found and evaluation == "CORRECT":
        effective_evaluation = "PARTIALLY_CORRECT"

    effective_response_strategy: ResponseStrategy = response_strategy
    effective_hint_level: HintLevel | None = hint_level
    if canvas_mistake_found:
        effective_response_strategy = select_response_strategy(
            intent=intent,
            evaluation=effective_evaluation,
            current_phase=request.current_phase,
            attempt_count=request.attempt_count,
            rules=rules,
        )
        effective_hint_level = select_hint_level(
            response_strategy=effective_response_strategy,
            current_hint_level=request.current_hint_level,
            attempt_count=request.attempt_count,
        )

    return TutorDecision(
        intent=intent,
        evaluation=effective_evaluation,
        error_type=effective_error_type,
        response_strategy=effective_response_strategy,
        hint_level=effective_hint_level,
        canvas_review=canvas_review,
    )


def build_canvas_wording_context(
    canvas_review: CanvasMathReview | None,
    canvas_regions: list[CanvasTextRegion],
) -> dict[str, object] | None:
    if canvas_review is None:
        return None
    classification = canvas_review.mistake_classification
    if classification.status != "mistake_found" or classification.mistake_step_id is None:
        return None

    target_index: int | None = None
    for index, region in enumerate(canvas_regions):
        if region.step_id == classification.mistake_step_id:
            target_index = index
            break
    if target_index is None:
        return None

    return {
        "channel": "CANVAS",
        "mistake_step_id": classification.mistake_step_id,
        "previous_step": canvas_regions[target_index - 1].text if target_index > 0 else None,
        "incorrect_step": canvas_regions[target_index].text,
        "target_text": classification.target_text,
        "feedback_goal": canvas_review.tutor_feedback,
        "answer_reveal_allowed": False,
    }


def build_tutor_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    decision: TutorDecision,
    answer_reveal_allowed: bool,
    confidence: float,
    tutor_message_override: str | None,
    voice_message_override: str | None,
) -> TutorResponse:
    canvas_review: CanvasMathReview | None = decision.canvas_review
    fallback_message: str = build_tutor_message(
        decision.intent,
        decision.evaluation,
        decision.error_type,
        decision.response_strategy,
        request.attempt_count,
        rules,
    )
    canvas_fallback: str | None = (
        canvas_review.tutor_feedback if canvas_review is not None else None
    )
    tutor_message: str = (
        tutor_message_override
        if tutor_message_override is not None
        else canvas_fallback or fallback_message
    )
    voice_message: str = voice_message_override if voice_message_override is not None else tutor_message
    events: list[StudentModelEvent] = []
    if should_emit_student_model_event(decision):
        events = [
            build_student_model_event(
                decision.evaluation,
                decision.error_type,
                decision.hint_level,
            )
        ]
    visual_cue: VisualCue = select_visual_cue(
        error_type=decision.error_type,
        response_strategy=decision.response_strategy,
        current_phase=request.current_phase,
        rules=rules,
    )
    mistake_classification: CanvasMistakeClassification | None = (
        canvas_review.mistake_classification if canvas_review is not None else None
    )
    canvas_feedback: CanvasFeedback = (
        canvas_review.canvas_feedback
        if canvas_review is not None
        else CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None)
    )
    annotation_intents: list[CanvasAnnotationIntent] = (
        canvas_review.annotation_intents if canvas_review is not None else []
    )

    response: TutorResponse = TutorResponse(
        evaluation=decision.evaluation,
        error_type=decision.error_type,
        intent=decision.intent,
        response_strategy=decision.response_strategy,
        tutor_message=tutor_message,
        tutor_message_voice_optimised=voice_message,
        voice_optimised=True,
        hint_level=decision.hint_level,
        scaffold_steps_delivered=[],
        visual_cue=visual_cue,
        canvas_feedback=canvas_feedback,
        mistake_classification=mistake_classification,
        annotation_intents=annotation_intents,
        next_phase_recommendation=request.current_phase,
        answer_reveal_allowed=answer_reveal_allowed,
        confidence=confidence,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        safety_check=safety_check,
        guardrail_check=GuardrailCheck(passed=True, violation_type=None, action_taken=None),
        student_model_events=events,
        attempt_increment=select_attempt_increment(decision),
        recommended_conversation_action=select_conversation_action(decision),
        question_completed=(
            request.question_completed or decision.evaluation == "CORRECT"
        ),
    )
    return apply_answer_reveal_guardrail(response, request.correct_answer, rules)


def select_visual_cue(
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    current_phase: LearningPhase,
    rules: ClassifierRulesConfig,
) -> VisualCue:
    if error_type is None:
        return VisualCue(show=False, cue_type=None, description=None)
    if response_strategy not in rules.visual_cue_rules.enabled_response_strategies:
        return VisualCue(show=False, cue_type=None, description=None)
    if current_phase not in rules.visual_cue_rules.enabled_phases:
        return VisualCue(show=False, cue_type=None, description=None)
    if error_type not in rules.visual_cue_rules.cues:
        return VisualCue(show=False, cue_type=None, description=None)

    cue_rule = rules.visual_cue_rules.cues[error_type]
    return VisualCue(show=True, cue_type=cue_rule.cue_type, description=cue_rule.description)


def apply_answer_reveal_guardrail(
    response: TutorResponse,
    correct_answer: str,
    rules: ClassifierRulesConfig,
) -> TutorResponse:
    if response.answer_reveal_allowed is True:
        return response
    if contains_answer_reveal(response.tutor_message, correct_answer, rules) is False:
        return response

    if response.evaluation == "CORRECT":
        return response.model_copy(
            update={
                "response_strategy": "CONFIRM_CORRECT",
                "tutor_message": rules.messages.CORRECT,
                "tutor_message_voice_optimised": rules.messages.CORRECT,
                "guardrail_check": GuardrailCheck(
                    passed=True,
                    violation_type=None,
                    action_taken=None,
                ),
            }
        )

    safe_strategy: ResponseStrategy = "CLARIFY"
    if response.intent not in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE"}:
        safe_strategy = "GUIDED_HINT"

    guardrail_check: GuardrailCheck = GuardrailCheck(
        passed=False,
        violation_type=rules.answer_reveal_guardrail.flag_type,
        action_taken=rules.answer_reveal_guardrail.action_taken,
    )
    return response.model_copy(
        update={
            "response_strategy": safe_strategy,
            "tutor_message": rules.answer_reveal_guardrail.safe_message,
            "tutor_message_voice_optimised": rules.answer_reveal_guardrail.safe_message,
            "answer_reveal_allowed": False,
            "guardrail_check": guardrail_check,
        }
    )


def apply_retrieved_hint(
    response: TutorResponse,
    hint_text: str,
    voice_text: str | None,
    correct_answer: str,
    rules: ClassifierRulesConfig,
) -> TutorResponse:
    updated_response: TutorResponse = response.model_copy(
        update={
            "tutor_message": hint_text,
            "tutor_message_voice_optimised": voice_text if voice_text is not None else hint_text,
        }
    )
    return apply_answer_reveal_guardrail(updated_response, correct_answer, rules)


def contains_answer_reveal(message: str, correct_answer: str, rules: ClassifierRulesConfig) -> bool:
    normalized_message: str = normalize_text(message)
    normalized_correct_answer: str = normalize_text(correct_answer)
    correct_value: float | None = extract_last_number(correct_answer)

    if normalized_correct_answer != "" and normalized_correct_answer in normalized_message:
        return True
    if contains_any(normalized_message, rules.answer_reveal_guardrail.reveal_phrases):
        return True
    if correct_value is None:
        return False

    correct_number: str = format_number_for_matching(correct_value)
    return re.search(rf"(?<![\d.])-?{re.escape(correct_number)}(?![\d.])", normalized_message) is not None


def detects_direct_answer_request(normalized_input: str, rules: ClassifierRulesConfig) -> bool:
    return contains_any(normalized_input, rules.answer_reveal_guardrail.direct_request_phrases)


def detects_override_attempt(normalized_input: str, rules: ClassifierRulesConfig) -> bool:
    return contains_any(normalized_input, rules.answer_reveal_guardrail.override_phrases)


def build_tutor_message(
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    attempt_count: int,
    rules: ClassifierRulesConfig,
) -> str:
    if intent == "ACKNOWLEDGEMENT":
        return rules.messages.CONTEXTUAL_ACKNOWLEDGEMENT
    if response_strategy == "SAFETY_RESPONSE":
        return rules.messages.SAFETY_RESPONSE
    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE"}:
        return rules.messages.REQUESTING_ANSWER_OR_OVERRIDE
    if intent == "REQUESTING_HINT":
        return rules.messages.REQUESTING_HINT
    if intent == "EXPRESSING_CONFUSION":
        return rules.messages.EXPRESSING_CONFUSION
    if intent == "OFF_TOPIC":
        return rules.messages.OFF_TOPIC
    if evaluation == "CORRECT":
        return rules.messages.CORRECT
    if evaluation == "UNCLEAR":
        return rules.messages.UNCLEAR
    if evaluation == "NO_ATTEMPT":
        return rules.messages.NO_ATTEMPT
    if evaluation == "IRRELEVANT":
        return rules.messages.IRRELEVANT
    if error_type is not None and error_type in rules.progressive_hint_messages:
        messages: list[str] = rules.progressive_hint_messages[error_type]
        if len(messages) > 0:
            message_index: int = min(max(attempt_count, 1), len(messages)) - 1
            return messages[message_index]
    if error_type == "ARITHMETIC_ERROR":
        return rules.messages.ARITHMETIC_ERROR
    if error_type == "SIGN_ERROR":
        return rules.messages.SIGN_ERROR
    if error_type == "OPPOSITE_OPERATION_ERROR":
        return rules.messages.OPPOSITE_OPERATION_ERROR
    if error_type == "CONCEPTUAL_MISUNDERSTANDING":
        return rules.messages.CONCEPTUAL_MISUNDERSTANDING
    if error_type == "PROCEDURAL_ERROR":
        return rules.messages.PROCEDURAL_ERROR
    if error_type == "NOTATION_ISSUE":
        return rules.messages.NOTATION_ISSUE
    if error_type == "INSUFFICIENT_INFORMATION":
        return rules.messages.INSUFFICIENT_INFORMATION

    return rules.messages.DEFAULT


def build_student_model_event(
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    hint_level: HintLevel | None,
) -> StudentModelEvent:
    event_type: LearningEventType = select_event_type(evaluation, hint_level)

    return StudentModelEvent(
        event_type=event_type,
        evaluation=evaluation,
        error_type=error_type,
        hint_level_used=hint_level if hint_level is not None else 0,
        independent_success=evaluation == "CORRECT" and hint_level is None,
    )


def select_event_type(evaluation: EvaluationCategory | None, hint_level: HintLevel | None) -> LearningEventType:
    if hint_level is not None:
        return "HINT_USED"
    if evaluation == "CORRECT":
        return "CORRECT_ATTEMPT"
    if evaluation == "PARTIALLY_CORRECT":
        return "PARTIAL_ATTEMPT"
    if evaluation == "INCORRECT":
        return "INCORRECT_ATTEMPT"

    return "SESSION_STARTED"


def is_contextual_acknowledgement(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    if request.question_completed is False or request.conversation_state is None:
        return False
    if (
        request.conversation_state.last_tutor_action != "CONFIRMED_CORRECT_ANSWER"
        or request.conversation_state.expected_student_response
        != "ACKNOWLEDGEMENT_OR_CONTINUE"
    ):
        return False
    normalized_input: str = re.sub(
        r"[^a-z0-9\s]",
        "",
        request.student_input.lower(),
    ).strip()
    return normalized_input in rules.conversation_rules.acknowledgement_phrases


def should_emit_student_model_event(decision: TutorDecision) -> bool:
    if decision.intent == "ACKNOWLEDGEMENT":
        return False
    if decision.hint_level is not None:
        return True
    return decision.evaluation in {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT"}


def select_attempt_increment(decision: TutorDecision) -> int:
    if decision.intent == "ACKNOWLEDGEMENT":
        return 0
    return int(
        decision.evaluation in {"CORRECT", "PARTIALLY_CORRECT", "INCORRECT"}
    )


def select_conversation_action(decision: TutorDecision) -> ConversationAction:
    if decision.intent == "ACKNOWLEDGEMENT" or decision.evaluation == "CORRECT":
        return "ADVANCE_TO_NEXT_QUESTION"
    if decision.response_strategy == "GUIDED_HINT":
        return "GIVE_HINT"
    if decision.response_strategy == "CLARIFY":
        return "REQUEST_CLARIFICATION"
    if decision.response_strategy in {"DIAGNOSTIC_PROMPT", "ENCOURAGE_RETRY"}:
        return "ASK_QUESTION"
    return "WAIT_FOR_STUDENT"


def build_contextual_acknowledgement_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
) -> TutorResponse:
    message: str = rules.messages.CONTEXTUAL_ACKNOWLEDGEMENT
    return TutorResponse(
        evaluation=None,
        error_type=None,
        intent="ACKNOWLEDGEMENT",
        response_strategy="CONTINUE",
        tutor_message=message,
        tutor_message_voice_optimised=message,
        voice_optimised=True,
        hint_level=None,
        scaffold_steps_delivered=[],
        visual_cue=VisualCue(show=False, cue_type=None, description=None),
        canvas_feedback=CanvasFeedback(
            has_feedback=False,
            step_feedback=[],
            highlight_instruction=None,
        ),
        mistake_classification=None,
        annotation_intents=[],
        next_phase_recommendation=request.current_phase,
        answer_reveal_allowed=False,
        confidence=rules.confidence.standard_response,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        safety_check=safety_check,
        guardrail_check=GuardrailCheck(
            passed=True,
            violation_type=None,
            action_taken=None,
        ),
        student_model_events=[],
        attempt_increment=0,
        recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION",
        question_completed=True,
    )


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def contains_any(value: str, phrases: Sequence[str]) -> bool:
    return any(phrase in value for phrase in phrases)


def is_low_confidence(transcript_confidence: float | None, rules: ClassifierRulesConfig) -> bool:
    if transcript_confidence is None:
        return False
    return transcript_confidence < rules.low_transcript_confidence_threshold


def is_ambiguous_answer(normalized_input: str, rules: ClassifierRulesConfig) -> bool:
    return contains_any(normalized_input, rules.answer_patterns.ambiguous)


def is_value_only_correct(request: ClassificationRequest) -> bool:
    normalized_input: str = normalize_text(request.student_input)
    correct_value: float | None = extract_last_number(request.correct_answer)

    if correct_value is None:
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", normalized_input) is None:
        return False

    return extract_last_number(normalized_input) == correct_value


def is_voice_value_only_correct(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    if request.input_source != "VOICE":
        return False

    normalized_input: str = normalize_answer_input(request, rules).strip(" .!,")
    correct_value: float | None = extract_last_number(request.correct_answer)
    if re.fullmatch(r"-?\d+(\.\d+)?", normalized_input) is None:
        return False
    return extract_last_number(normalized_input) == correct_value


def is_correct_answer(request: ClassificationRequest, rules: ClassifierRulesConfig) -> bool:
    normalized_input: str = normalize_answer_input(request, rules)
    correct_value: float | None = extract_last_number(request.correct_answer)
    student_value: float | None = extract_last_number(normalized_input)

    if correct_value is None or student_value != correct_value:
        return False

    return contains_any(normalized_input, rules.answer_patterns.answer_notation)


def normalize_answer_input(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> str:
    normalized_input: str = normalize_text(request.student_input)
    if request.input_source != "VOICE":
        return normalized_input

    for spoken_number, number_value in rules.answer_patterns.spoken_number_values.items():
        normalized_input = re.sub(
            rf"\b{re.escape(spoken_number)}\b",
            format_number_for_matching(number_value),
            normalized_input,
        )
    return normalized_input


def has_visible_correct_method(normalized_input: str, rules: ClassifierRulesConfig) -> bool:
    return contains_any(normalized_input, rules.answer_patterns.correct_method)


def is_addition_opposite_operation_error(
    request: ClassificationRequest,
    student_value: float | None,
    correct_value: float | None,
) -> bool:
    if student_value is None or correct_value is None:
        return False

    match: re.Match[str] | None = re.search(
        r"\bx\s*\+\s*(-?\d+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)\b",
        request.question,
        flags=re.IGNORECASE,
    )
    if match is None:
        return False

    added_value: float = float(match.group(1))
    right_side: float = float(match.group(2))
    expected_correct_value: float = right_side - added_value
    expected_wrong_value: float = right_side + added_value
    return correct_value == expected_correct_value and student_value == expected_wrong_value


def extract_last_number(value: str) -> float | None:
    matches: list[str] = re.findall(r"-?\d+(?:\.\d+)?", value)
    if len(matches) == 0:
        return None
    return float(matches[-1])


def format_number_for_matching(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)


def normalize_number_text(value: str) -> str:
    number: float = float(value)
    return format_number_for_matching(number)
