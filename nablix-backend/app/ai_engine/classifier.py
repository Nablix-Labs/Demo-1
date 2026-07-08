from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.ai_engine.schemas import (
    CanvasAnnotationIntent,
    CanvasFeedback,
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

if TYPE_CHECKING:
    from app.ai_engine.openai_client import (
        OpenAIAIEngineClient,
        OpenAIAnswerEvaluation,
        OpenAIErrorDiagnosis,
        OpenAITutorMessage,
    )


class ClassificationRequest(StrictSchema):
    question: str
    correct_answer: str
    student_input: str
    current_phase: LearningPhase
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    current_hint_level: HintLevel | None
    concept_id: str | None = None
    difficulty: str = "FOUNDATION"
    max_hint_results: int = Field(default=3, ge=1)
    exclude_content_ids: list[str] = Field(default_factory=list)
    canvas_regions: list[CanvasTextRegion] = Field(default_factory=list)


def classify_student_response(request: ClassificationRequest) -> TutorResponse:
    rules: ClassifierRulesConfig = load_classifier_rules()
    settings: Settings = get_settings()
    openai_client: OpenAIAIEngineClient | None = build_openai_ai_engine_client(settings)
    safety_check: SafetyCheck = check_student_message_safety(request.student_input, rules)
    intent: IntentType = detect_student_intent(request.student_input, rules)

    if safety_check.passed is False:
        return build_tutor_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            intent=intent,
            evaluation=None,
            error_type=None,
            response_strategy="SAFETY_RESPONSE",
            hint_level=None,
            answer_reveal_allowed=False,
            confidence=rules.confidence.safety_response,
            tutor_message_override=None,
            voice_message_override=None,
        )

    evaluation: EvaluationCategory | None = evaluate_answer_attempt(request, intent, rules)
    openai_evaluation: OpenAIAnswerEvaluation | None = evaluate_answer_with_openai(
        request=request,
        intent=intent,
        rules=rules,
        openai_client=openai_client,
    )
    if openai_evaluation is not None:
        evaluation = openai_evaluation.evaluation

    error_type: ErrorType | None = classify_student_error(request, evaluation, rules)
    openai_error: OpenAIErrorDiagnosis | None = diagnose_error_with_openai(
        request=request,
        evaluation=evaluation,
        openai_client=openai_client,
    )
    if openai_error is not None:
        error_type = openai_error.error_type

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
    openai_message: OpenAITutorMessage | None = build_tutor_message_with_openai(
        request=request,
        intent=intent,
        evaluation=evaluation,
        error_type=error_type,
        response_strategy=response_strategy,
        hint_level=hint_level,
        openai_client=openai_client,
    )
    return build_tutor_response(
        request=request,
        rules=rules,
        safety_check=safety_check,
        intent=intent,
        evaluation=evaluation,
        error_type=error_type,
        response_strategy=response_strategy,
        hint_level=hint_level,
        answer_reveal_allowed=False,
        confidence=rules.confidence.standard_response,
        tutor_message_override=openai_message.tutor_message if openai_message is not None else None,
        voice_message_override=(
            openai_message.tutor_message_voice_optimised if openai_message is not None else None
        ),
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
    )


def evaluate_answer_with_openai(
    request: ClassificationRequest,
    intent: IntentType,
    rules: ClassifierRulesConfig,
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAIAnswerEvaluation | None:
    if openai_client is None:
        return None
    if intent != "SUBMITTING_ANSWER":
        return None
    if request.input_source == "CANVAS":
        return None
    if request.input_source == "VOICE" and is_low_confidence(request.transcript_confidence, rules):
        return None
    if normalize_text(request.student_input) == "":
        return None

    try:
        return openai_client.evaluate_answer(
            question=request.question,
            correct_answer=request.correct_answer,
            student_input=request.student_input,
        )
    except AdapterError as error:
        logger.warning(
            "openai_ai_engine_fallback",
            extra={"step": "answer_evaluation", "detail": error.message},
        )
        return None


def diagnose_error_with_openai(
    request: ClassificationRequest,
    evaluation: EvaluationCategory | None,
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAIErrorDiagnosis | None:
    if openai_client is None:
        return None
    if request.input_source == "CANVAS":
        return None
    if evaluation not in {"INCORRECT", "PARTIALLY_CORRECT"}:
        return None

    try:
        return openai_client.diagnose_error(
            question=request.question,
            correct_answer=request.correct_answer,
            student_input=request.student_input,
        )
    except AdapterError as error:
        logger.warning(
            "openai_ai_engine_fallback",
            extra={"step": "error_diagnosis", "detail": error.message},
        )
        return None


def build_tutor_message_with_openai(
    request: ClassificationRequest,
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    hint_level: HintLevel | None,
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAITutorMessage | None:
    if openai_client is None:
        return None
    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE"}:
        return None
    if request.input_source == "CANVAS":
        return None

    try:
        return openai_client.build_tutor_message(
            question=request.question,
            student_input=request.student_input,
            evaluation=evaluation,
            error_type=error_type,
            response_strategy=response_strategy,
            hint_level=hint_level,
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
    normalized_input: str = normalize_text(request.student_input)

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

    normalized_input: str = normalize_text(request.student_input)
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


def build_tutor_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    hint_level: HintLevel | None,
    answer_reveal_allowed: bool,
    confidence: float,
    tutor_message_override: str | None,
    voice_message_override: str | None,
) -> TutorResponse:
    fallback_message: str = build_tutor_message(intent, evaluation, error_type, response_strategy, rules)
    tutor_message: str = tutor_message_override if tutor_message_override is not None else fallback_message
    voice_message: str = voice_message_override if voice_message_override is not None else tutor_message
    event: StudentModelEvent = build_student_model_event(evaluation, error_type, hint_level)
    visual_cue: VisualCue = select_visual_cue(
        error_type=error_type,
        response_strategy=response_strategy,
        current_phase=request.current_phase,
        rules=rules,
    )
    mistake_classification: CanvasMistakeClassification | None = classify_canvas_mistake(
        request=request,
        intent=intent,
        evaluation=evaluation,
        rules=rules,
    )
    annotation_intents: list[CanvasAnnotationIntent] = build_canvas_annotation_intents(
        mistake_classification=mistake_classification,
        canvas_regions=request.canvas_regions,
    )

    response: TutorResponse = TutorResponse(
        evaluation=evaluation,
        error_type=error_type,
        intent=intent,
        response_strategy=response_strategy,
        tutor_message=tutor_message,
        tutor_message_voice_optimised=voice_message,
        voice_optimised=True,
        hint_level=hint_level,
        scaffold_steps_delivered=[],
        visual_cue=visual_cue,
        canvas_feedback=CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None),
        mistake_classification=mistake_classification,
        annotation_intents=annotation_intents,
        next_phase_recommendation=request.current_phase,
        answer_reveal_allowed=answer_reveal_allowed,
        confidence=confidence,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        safety_check=safety_check,
        guardrail_check=GuardrailCheck(passed=True, violation_type=None, action_taken=None),
        student_model_events=[event],
    )
    return apply_answer_reveal_guardrail(response, request.correct_answer, rules)


def classify_canvas_mistake(
    request: ClassificationRequest,
    intent: IntentType,
    evaluation: EvaluationCategory | None,
    rules: ClassifierRulesConfig,
) -> CanvasMistakeClassification | None:
    if request.input_source != "CANVAS":
        return None
    if len(request.canvas_regions) == 0:
        return CanvasMistakeClassification(
            status="uncertain",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=rules.confidence.standard_response,
        )
    if intent in {"REQUESTING_ANSWER", "ATTEMPTING_OVERRIDE", "OFF_TOPIC", "REQUESTING_HINT", "ASKING_QUESTION"}:
        return None
    if has_uncertain_canvas_text(request.canvas_regions):
        return CanvasMistakeClassification(
            status="uncertain",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=rules.confidence.standard_response,
        )
    # Root cause outranks symptom: a wrong inverse operand explains the wrong
    # final answer that follows from it, so scan for it first.
    inverse_operand: str | None = extract_addition_inverse_operand(request.question)
    if evaluation in {"INCORRECT", "PARTIALLY_CORRECT"} and inverse_operand is not None:
        for index, region in enumerate(request.canvas_regions):
            mistake: CanvasMistakeClassification | None = classify_inverse_operand_mistake(
                region=region,
                fallback_step_id=f"step-{index + 1}",
                expected_operand=inverse_operand,
                confidence=rules.confidence.standard_response,
            )
            if mistake is not None:
                return mistake

    expected_answer: str | None = extract_variable_answer(request.correct_answer)
    if expected_answer is not None:
        for index, region in enumerate(request.canvas_regions):
            mistake: CanvasMistakeClassification | None = classify_wrong_variable_answer_step(
                region=region,
                fallback_step_id=f"step-{index + 1}",
                expected_answer=expected_answer,
                confidence=rules.confidence.standard_response,
            )
            if mistake is not None:
                return mistake

    if evaluation == "CORRECT":
        return CanvasMistakeClassification(
            status="no_mistake",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=rules.confidence.standard_response,
        )
    if evaluation not in {"INCORRECT", "PARTIALLY_CORRECT"}:
        return None

    if inverse_operand is None:
        return CanvasMistakeClassification(
            status="uncertain",
            mistake_step_id=None,
            target_text=None,
            target_span=None,
            replacement_text=None,
            confidence=rules.confidence.standard_response,
        )

    return CanvasMistakeClassification(
        status="uncertain",
        mistake_step_id=None,
        target_text=None,
        target_span=None,
        replacement_text=None,
        confidence=rules.confidence.standard_response,
    )


def has_uncertain_canvas_text(canvas_regions: list[CanvasTextRegion]) -> bool:
    return any(region.confidence < 0.75 or "?" in region.text for region in canvas_regions)


def extract_addition_inverse_operand(question: str) -> str | None:
    pattern: str = r"\bx\s*\+\s*(-?\d+(?:\.\d+)?)\s*=\s*-?\d+(?:\.\d+)?"
    match: re.Match[str] | None = re.search(pattern, question, flags=re.IGNORECASE)
    if match is None:
        return None
    return normalize_number_text(match.group(1))


def extract_variable_answer(answer: str) -> str | None:
    pattern: str = r"\bx\s*=\s*(-?\d+(?:\.\d+)?)\b"
    match: re.Match[str] | None = re.search(pattern, answer, flags=re.IGNORECASE)
    if match is None:
        return None
    return normalize_number_text(match.group(1))


# Handwritten OCR often mangles the variable glyph ("x" → "K", ")(") and may use
# unicode minus. Normalise dashes (length-preserving, so spans stay valid) and
# anchor matches on the "=" instead of trusting the variable character.
_DASH_TRANSLATION = str.maketrans({"−": "-", "–": "-", "—": "-"})


def _normalized_region_text(region: CanvasTextRegion) -> str:
    return region.text.translate(_DASH_TRANSLATION)


def classify_wrong_variable_answer_step(
    region: CanvasTextRegion,
    fallback_step_id: str,
    expected_answer: str,
    confidence: float,
) -> CanvasMistakeClassification | None:
    pattern: str = r"^\s*\S{0,2}\s*=\s*(-?\d+(?:\.\d+)?)\s*$"
    match: re.Match[str] | None = re.search(pattern, _normalized_region_text(region), flags=re.IGNORECASE)
    if match is None:
        return None

    actual_answer: str = normalize_number_text(match.group(1))
    if actual_answer == expected_answer:
        return None

    target_span_tuple: tuple[int, int] = match.span(1)
    return CanvasMistakeClassification(
        status="mistake_found",
        mistake_step_id=region.step_id if region.step_id is not None else fallback_step_id,
        target_text=region.text[target_span_tuple[0] : target_span_tuple[1]],
        target_span=[target_span_tuple[0], target_span_tuple[1]],
        replacement_text=expected_answer,
        confidence=confidence,
    )


def classify_inverse_operand_mistake(
    region: CanvasTextRegion,
    fallback_step_id: str,
    expected_operand: str,
    confidence: float,
) -> CanvasMistakeClassification | None:
    pattern: str = r"=\s*-?\d+(?:\.\d+)?\s*([+-])\s*(-?\d+(?:\.\d+)?)\b"
    match: re.Match[str] | None = re.search(pattern, _normalized_region_text(region), flags=re.IGNORECASE)
    if match is None:
        return None

    operator: str = match.group(1)
    actual_operand: str = normalize_number_text(match.group(2))
    if operator == "-" and actual_operand == expected_operand:
        return None

    if operator == "-":
        # Right operation, wrong operand ("x = 9 - 5"): replace just the operand.
        start, end = match.span(2)
        replacement_text: str = expected_operand
    else:
        # Wrong inverse operation ("x = 9 + 6"): replace the whole "+ 6" span.
        start, end = match.start(1), match.end(2)
        replacement_text = f"-{expected_operand}"

    return CanvasMistakeClassification(
        status="mistake_found",
        mistake_step_id=region.step_id if region.step_id is not None else fallback_step_id,
        target_text=region.text[start:end],
        target_span=[start, end],
        replacement_text=replacement_text,
        confidence=confidence,
    )


def build_canvas_annotation_intents(
    mistake_classification: CanvasMistakeClassification | None,
    canvas_regions: list[CanvasTextRegion],
) -> list[CanvasAnnotationIntent]:
    if mistake_classification is None or mistake_classification.status != "mistake_found":
        return []
    if mistake_classification.mistake_step_id is None:
        return []

    correction_text: str | None = build_canvas_correction_text(
        mistake_classification=mistake_classification,
        canvas_regions=canvas_regions,
    )
    intents: list[CanvasAnnotationIntent] = [
        CanvasAnnotationIntent(
            kind="circle_target",
            target_step_id=mistake_classification.mistake_step_id,
            text=None,
            placement=None,
        )
    ]
    if correction_text is not None:
        intents.append(
            CanvasAnnotationIntent(
                kind="write_correction",
                target_step_id=mistake_classification.mistake_step_id,
                text=correction_text,
                placement="right",
            )
        )
        # Arrow only makes sense pointing at a written correction.
        intents.append(
            CanvasAnnotationIntent(
                kind="draw_arrow",
                target_step_id=mistake_classification.mistake_step_id,
                text=None,
                placement=None,
            )
        )
    return intents


def build_canvas_correction_text(
    mistake_classification: CanvasMistakeClassification,
    canvas_regions: list[CanvasTextRegion],
) -> str | None:
    if mistake_classification.target_span is None or mistake_classification.replacement_text is None:
        return None
    region: CanvasTextRegion | None = find_canvas_region(canvas_regions, mistake_classification.mistake_step_id)
    if region is None:
        return None

    start, end = mistake_classification.target_span
    if start < 0 or end > len(region.text) or start >= end:
        return None
    return f"{region.text[:start]}{mistake_classification.replacement_text}{region.text[end:]}"


def find_canvas_region(canvas_regions: list[CanvasTextRegion], step_id: str | None) -> CanvasTextRegion | None:
    if step_id is None:
        return None
    for region in canvas_regions:
        if region.step_id == step_id:
            return region
    return None


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
    rules: ClassifierRulesConfig,
) -> str:
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
        independent_success=evaluation == "CORRECT",
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


def is_correct_answer(request: ClassificationRequest, rules: ClassifierRulesConfig) -> bool:
    normalized_input: str = normalize_text(request.student_input)
    correct_value: float | None = extract_last_number(request.correct_answer)
    student_value: float | None = extract_last_number(normalized_input)

    if correct_value is None or student_value != correct_value:
        return False

    return contains_any(normalized_input, rules.answer_patterns.answer_notation)


def has_visible_correct_method(normalized_input: str, rules: ClassifierRulesConfig) -> bool:
    return contains_any(normalized_input, rules.answer_patterns.correct_method)


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
