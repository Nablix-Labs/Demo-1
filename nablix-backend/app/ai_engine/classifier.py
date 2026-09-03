from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from app.ai_engine.canvas_math_review import (
    normalize_canvas_math_text,
    review_canvas_math,
)
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.ai_engine.prompt_registry import Trigger
from app.ai_engine.schemas import (
    CanvasAnnotationIntent,
    CanvasFeedback,
    CanvasMathReview,
    CanvasMistakeClassification,
    CanvasTextRegion,
    ErrorType,
    EvaluationCategory,
    ExplainAgainRequest,
    ExplainAgainResult,
    GuardrailCheck,
    HintLevel,
    InputSource,
    IntentType,
    LearningEventType,
    LearningPhase,
    IndependentOutcome,
    Phase3ReviewEvidence,
    ResponseStrategy,
    SafetyCheck,
    StrictSchema,
    StudentModelEvent,
    TutorResponse,
    VisualCue,
)
from app.core.config import Settings, get_settings
from app.services.question_anchors import plan_question_anchors
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import (
    ConversationAction,
    ConversationMessage,
    ConversationState,
    Phase2PromptContext,
    SpatialMathToken,
)
from app.models.canvas_memory import CanvasEvent
from app.models.guided_learning import (
    ActiveTeachingObjective,
    FocusedComponentEvidence,
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedEvidenceClaim,
    GuidedEvidenceSource,
    GuidedEvaluation,
    GuidedCanvasEvidence,
    GuidedPedagogicalMove,
    GuidedPromptType,
    GuidedRescueContext,
    GuidedStudentState,
    GuidedTeachingState,
    GuidedTeachingPlanStep,
    GuidedTutorContext,
    ScaffoldEvaluationContext,
    ScaffoldStepEvaluation,
)
from app.models.student_model_session import AnswerSpec, QuestionType, SupportUsed

if TYPE_CHECKING:
    from app.ai_engine.openai_client import (
        OpenAIAIEngineClient,
        OpenAITutorMessage,
        OpenAITutorTurn,
    )


_CANVAS_EXPRESSION = re.compile(
    r"^(?:(?:[A-Za-z]|\d|\s|[+\-−×*/÷=().]|\\(?:times|cdot|div)))+$"
)
_CANVAS_LATEX_COMMAND = re.compile(r"\\(?:times|cdot|div)")
_CANVAS_EXPRESSION_FRAGMENT = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"[A-Za-z](?:\s*(?:[+\-−×*/÷=]|\\(?:times|cdot|div))\s*"
    r"(?:[A-Za-z]|\d+(?:\.\d+)?))+"
    r"|[+\-−×÷]\s*\d+(?:\.\d+)?"
    r")(?![A-Za-z0-9])"
)


class ClassificationRequest(StrictSchema):
    experiment_subject_id: str | None = None
    question_id: str | None = None
    question_type: QuestionType | None = None
    question: str
    correct_answer: str
    answer_spec: AnswerSpec | None = None
    phase_2_prompt_context: Phase2PromptContext | None = None
    student_input: str
    current_phase: LearningPhase
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    question_completed: bool = False
    answer_value_confirmed: bool = False
    question_number: int = Field(default=1, ge=1)
    current_hint_level: HintLevel | None
    concept_id: str | None = None
    difficulty: str = "FOUNDATION"
    max_hint_results: int = Field(default=3, ge=1)
    exclude_content_ids: list[str] = Field(default_factory=list)
    canvas_regions: list[CanvasTextRegion] = Field(default_factory=list)
    canvas_ocr_text: str | None = None
    canvas_ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    canvas_mathml_blocks: list[str] = Field(default_factory=list)
    spatial_tokens: list[SpatialMathToken] = Field(default_factory=list)
    canvas_events: list[CanvasEvent] = Field(default_factory=list)
    canvas_snapshot_reference: str | None = None
    canvas_strokes: list[dict[str, object]] = Field(default_factory=list)
    has_canvas_evidence: bool = False
    canvas_solution_complete_candidate: bool = False
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    conversation_state: ConversationState | None = None
    generated_question_rubric: GeneratedQuestionRubric | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    guided_teaching_state: GuidedTeachingState | None = None
    rescue_context: GuidedRescueContext | None = None
    scaffold_evaluation_context: ScaffoldEvaluationContext | None = None
    phase3_submission_confirmed: bool | None = None
    phase3_submission_kind: str | None = None
    phase3_allowed_error_definitions: list[dict[str, object]] = Field(default_factory=list)


@dataclass(frozen=True)
class TutorDecision:
    intent: IntentType
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    response_strategy: ResponseStrategy
    hint_level: HintLevel | None
    canvas_review: CanvasMathReview | None
    reasoning_complete: bool


def classify_student_response(request: ClassificationRequest) -> TutorResponse:
    rules: ClassifierRulesConfig = load_classifier_rules()
    settings: Settings = get_settings()
    selected_model = openai_model_for_request(settings, request)
    openai_client: OpenAIAIEngineClient | None = build_openai_ai_engine_client(
        settings.model_copy(update={"openai_ai_engine_model": selected_model})
    )
    safety_check: SafetyCheck = check_student_message_safety(request.student_input, rules)
    intent: IntentType = detect_student_intent(request.student_input, rules)

    if (
        request.current_phase == "INDEPENDENT_PRACTICE"
        and request.phase3_submission_confirmed is not None
    ):
        return classify_independent_practice_response(request, rules, safety_check, intent)

    if safety_check.passed is False:
        safety_decision = TutorDecision(
            intent=intent,
            evaluation=None,
            error_type=None,
            response_strategy="SAFETY_RESPONSE",
            hint_level=None,
            canvas_review=None,
            reasoning_complete=False,
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

    if (
        request.scaffold_evaluation_context is not None
        and not (
            request.input_source == "VOICE"
            and is_low_confidence(request.transcript_confidence, rules)
        )
        and openai_client is not None
    ):
        return classify_scaffold_response(
            request,
            rules,
            safety_check,
            openai_client,
            intent,
        )

    evaluation: EvaluationCategory | None = evaluate_answer_attempt(request, intent, rules)
    if (
        request.current_phase == "GUIDED_PRACTICE"
        and request.phase_2_prompt_context is not None
        and rules.guided_learning.evaluation_mode == "LLM_STATE_MACHINE"
        and settings.use_openai_ai_engine
        and openai_client is None
    ):
        raise AdapterError(
            "openai_ai_engine",
            "LLM_STATE_MACHINE is enabled but the OpenAI client is unavailable.",
        )
    if should_use_guided_state_machine(request, rules, openai_client, evaluation):
        if openai_client is None:
            raise AdapterError(
                "openai_ai_engine",
                "LLM_STATE_MACHINE requires an enabled OpenAI client.",
            )
        return classify_guided_learning_response(
            request=request,
            rules=rules,
            safety_check=safety_check,
            openai_client=openai_client,
            intent=intent,
        )
    authoritative_verification = (
        uses_authoritative_verification(request)
        or evaluate_answer_contract(request) == "CORRECT"
    )
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
            rules=rules,
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
        rules=rules,
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

    decision = build_openai_tutor_decision(
        request,
        rules,
        intent,
        evaluation,
        authoritative_verification,
        openai_turn,
    )
    use_openai_wording = (
        not authoritative_verification
        or openai_turn.evaluation == evaluation
    )
    return build_tutor_response(
        request=request,
        rules=rules,
        safety_check=safety_check,
        decision=decision,
        answer_reveal_allowed=False,
        confidence=openai_turn.confidence,
        tutor_message_override=(
            openai_turn.tutor_message if use_openai_wording else None
        ),
        voice_message_override=(
            openai_turn.tutor_message_voice_optimised
            if use_openai_wording
            else None
        ),
    )


def classify_scaffold_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    openai_client: OpenAIAIEngineClient,
    intent: IntentType,
) -> TutorResponse:
    context = request.scaffold_evaluation_context
    if context is None:
        raise AdapterError(
            "openai_ai_engine",
            "Scaffold evaluation context is required.",
        )
    last_error: AdapterError | None = None
    result: ScaffoldStepEvaluation | None = None
    for attempt in range(rules.guided_learning.scaffold_evaluation_maximum_retries + 1):
        try:
            result = openai_client.evaluate_scaffold_step(
                context=context,
                student_response=request.student_input,
                input_source=request.input_source,
                system_prompt=rules.guided_learning.scaffold_evaluator_system_prompt,
            )
            break
        except AdapterError as error:
            last_error = error
            logger.warning(
                "scaffold_evaluation_retry",
                extra={
                    "question_id": request.question_id,
                    "scaffold_id": context.scaffold_id,
                    "step_id": context.step_id,
                    "attempt": attempt + 1,
                    "detail": error.detail,
                },
            )
    if result is None:
        logger.error(
            "scaffold_evaluation_failed",
            extra={
                "question_id": request.question_id,
                "scaffold_id": context.scaffold_id,
                "step_id": context.step_id,
                "detail": last_error.detail if last_error is not None else None,
            },
        )
        result = ScaffoldStepEvaluation(
            step_satisfied=False,
            original_answer_correct=False,
            demonstrated_fact=None,
            confidence=0.0,
            tutor_message=rules.guided_learning.scaffold_evaluation_failure_message,
            tutor_message_voice=rules.guided_learning.scaffold_evaluation_failure_message,
        )
    satisfied = (
        result.step_satisfied
        and result.confidence >= rules.guided_learning.confidence_threshold
    )
    explanation_requested = intent in {"ASKING_QUESTION", "EXPRESSING_CONFUSION"}
    original_answer_correct = (
        False
        if explanation_requested
        else satisfied and result.original_answer_correct
    )
    tutor_message_override = (
        result.tutor_message
        if not message_reveals_answer(
            result.tutor_message,
            result.tutor_message_voice,
            context.canonical_answer,
            rules,
        )
        else None
    )
    logger.info(
        "scaffold_step_evaluated",
        extra={
            "question_id": request.question_id,
            "scaffold_id": context.scaffold_id,
            "step_id": context.step_id,
            "step_satisfied": satisfied,
            "original_answer_correct": original_answer_correct,
            "confidence": result.confidence,
            "detected_intent": intent,
            "explanation_requested": explanation_requested,
        },
    )
    decision = TutorDecision(
        intent=intent if explanation_requested else "SUBMITTING_ANSWER",
        evaluation=(
            None
            if explanation_requested
            else "CORRECT"
            if satisfied
            else "INCORRECT"
        ),
        error_type=(
            None
            if explanation_requested or satisfied
            else "INSUFFICIENT_INFORMATION"
        ),
        response_strategy=(
            "CLARIFY"
            if explanation_requested or not satisfied
            else "CONFIRM_CORRECT"
        ),
        hint_level=None,
        canvas_review=_canvas_review_for(request, rules, result.confidence),
        reasoning_complete=satisfied,
    )
    response = build_tutor_response(
        request=request,
        rules=rules,
        safety_check=safety_check,
        decision=decision,
        answer_reveal_allowed=False,
        confidence=result.confidence,
        tutor_message_override=tutor_message_override,
        voice_message_override=(
            result.tutor_message_voice if tutor_message_override is not None else None
        ),
    )
    return response.model_copy(
        update={
            "scaffold_original_answer_correct": original_answer_correct,
        }
    )


def classify_independent_practice_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    intent: IntentType,
) -> TutorResponse:
    """Evaluate a final independent submission without generating tutoring."""

    submitted = request.phase3_submission_confirmed is True
    kind = request.phase3_submission_kind
    canvas_unclear = (
        kind == "CANVAS"
        and (
            request.has_canvas_evidence is False
            or any(
                region.confidence < rules.canvas_review.min_region_confidence
                for region in request.canvas_regions
            )
        )
    )
    evaluation = evaluate_answer_attempt(request, intent, rules) if submitted else None
    if not submitted or kind not in {"CANVAS", "CHOICE"}:
        outcome: IndependentOutcome = "AWAITING_SUBMISSION"
    elif canvas_unclear or evaluation in {"UNCLEAR", "NO_ATTEMPT", None}:
        outcome = "INPUT_UNCLEAR" if kind == "CANVAS" else "AWAITING_SUBMISSION"
    elif evaluation == "CORRECT":
        outcome = "INDEPENDENTLY_VERIFIED"
    else:
        outcome = "RESCUE_REQUIRED"
    terminal = outcome in {"INDEPENDENTLY_VERIFIED", "RESCUE_REQUIRED"}
    response_evaluation: EvaluationCategory | None = (
        "CORRECT" if outcome == "INDEPENDENTLY_VERIFIED"
        else "INCORRECT" if outcome == "RESCUE_REQUIRED"
        else "UNCLEAR" if outcome == "INPUT_UNCLEAR"
        else None
    )
    message = (
        rules.independent_practice.answer_recorded_message
        if outcome == "INDEPENDENTLY_VERIFIED"
        else rules.independent_practice.rescue_required_message
        if outcome == "RESCUE_REQUIRED"
        else rules.independent_practice.input_unclear_message
        if outcome == "INPUT_UNCLEAR"
        else rules.independent_practice.awaiting_submission_message
    )
    first_error_step = (
        request.canvas_regions[0].step_id
        if outcome == "RESCUE_REQUIRED" and kind == "CANVAS" and request.canvas_regions
        else None
    )
    generic_error = (
        classify_student_error(request, response_evaluation, rules)
        if outcome == "RESCUE_REQUIRED"
        else None
    )
    return TutorResponse(
        evaluation=response_evaluation,
        error_type=generic_error,
        intent="SUBMITTING_ANSWER" if submitted else intent,
        response_strategy="CONFIRM_CORRECT" if outcome == "INDEPENDENTLY_VERIFIED" else "CLARIFY",
        tutor_message=message,
        tutor_message_voice_optimised="",
        voice_optimised=True,
        hint_level=None,
        scaffold_steps_delivered=[],
        visual_cue=VisualCue(show=False, cue_type=None, description=None),
        canvas_feedback=CanvasFeedback(has_feedback=False, step_feedback=[], highlight_instruction=None),
        mistake_classification=None,
        annotation_intents=[],
        next_phase_recommendation=request.current_phase,
        answer_reveal_allowed=False,
        confidence=rules.confidence.standard_response,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        safety_check=safety_check,
        guardrail_check=GuardrailCheck(passed=True, violation_type=None, action_taken=None),
        student_model_events=[],
        attempt_increment=1 if terminal else 0,
        recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION" if terminal else "WAIT_FOR_STUDENT",
        question_completed=terminal,
        answer_value_confirmed=outcome == "INDEPENDENTLY_VERIFIED",
        reasoning_complete=terminal,
        independent_outcome=outcome,
        independent_success=(outcome == "INDEPENDENTLY_VERIFIED") if terminal else None,
        independent_attempt_terminal=terminal,
        first_error_step=first_error_step,
        phase3_review_evidence=Phase3ReviewEvidence(
            question_id=request.question_id or "",
            submission_kind=kind if kind in {"CANVAS", "CHOICE"} else None,
            submitted_work_present=bool(request.student_input.strip()),
            ocr_clear=(not canvas_unclear) if kind == "CANVAS" else None,
            evaluation=response_evaluation,
            selected_error_code=None,
            first_error_step=first_error_step,
            confidence=rules.confidence.standard_response,
        ),
    )


def should_use_guided_state_machine(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    openai_client: OpenAIAIEngineClient | None,
    deterministic_evaluation: EvaluationCategory | None,
) -> bool:
    if (
        request.current_phase != "GUIDED_PRACTICE"
        or request.phase_2_prompt_context is None
        or rules.guided_learning.evaluation_mode != "LLM_STATE_MACHINE"
        or openai_client is None
    ):
        return False
    if request.input_source == "VOICE" and is_low_confidence(
        request.transcript_confidence,
        rules,
    ):
        return False
    if request.answer_spec is None or request.question_id is None:
        return False
    if teaching_steps_for(request):
        return True
    if (
        deterministic_evaluation == "CORRECT"
        and evaluate_answer_contract(request) == "CORRECT"
        and not requires_multi_component_completion(request, rules)
    ):
        return False
    method = request.answer_spec.verification_method
    return not (
        method == "EXACT_CHOICE_MATCH"
        and deterministic_evaluation in {"CORRECT", "INCORRECT"}
        and not requires_multi_component_completion(request, rules)
    )


def resolve_guided_rubric(
    question_id: str,
    question_type: QuestionType | None,
    question: str,
    answer_spec: AnswerSpec,
    potential_errors: list[dict[str, object]],
    target_micro_skill_ids: list[str],
    existing_rubric: GeneratedQuestionRubric | None,
    rules: ClassifierRulesConfig,
    openai_client: OpenAIAIEngineClient,
) -> GeneratedQuestionRubric:
    """Return the persisted runtime rubric or generate it once from existing content."""

    expression_role_rubric = expression_role_rubric_from_question(
        question_id,
        question_type,
        question,
        answer_spec,
        rules.guided_learning.rubric_prompt_version,
    )
    if expression_role_rubric is not None:
        return expression_role_rubric

    rubric = existing_rubric
    if rubric is not None and rubric.question_id == question_id:
        try:
            validate_generated_rubric(
                rubric,
                question_id,
                question_type,
                answer_spec,
                rules,
            )
            return rubric
        except AdapterError as error:
            logger.warning(
                "guided_persisted_rubric_replaced",
                extra={
                    "question_id": question_id,
                    "detail": error.detail,
                },
            )
            rubric = None

    authored_rubric = rubric_from_authored_answer_parts(
        question_id,
        question_type,
        answer_spec,
        rules.guided_learning.rubric_prompt_version,
    )
    if authored_rubric is not None:
        return authored_rubric

    if rubric is None or rubric.question_id != question_id:
        rubric_error: AdapterError | None = None
        for attempt in range(rules.guided_learning.maximum_retries + 1):
            try:
                rubric = openai_client.generate_guided_rubric(
                    question_id=question_id,
                    question_type=question_type,
                    question=question,
                    answer_spec=answer_spec,
                    potential_errors=potential_errors,
                    target_micro_skill_ids=target_micro_skill_ids,
                    prompt_version=rules.guided_learning.rubric_prompt_version,
                    system_prompt=rules.guided_learning.rubric_system_prompt,
                )
                validate_generated_rubric(
                    rubric,
                    question_id,
                    question_type,
                    answer_spec,
                    rules,
                )
                break
            except AdapterError as error:
                rubric_error = error
                logger.warning(
                    "guided_rubric_retry",
                    extra={
                        "question_id": question_id,
                        "attempt": attempt + 1,
                        "detail": error.detail,
                    },
                )
        if rubric is None:
            raise rubric_error or AdapterError(
                "openai_ai_engine",
                f"Rubric generation failed for {question_id}.",
            )
    validate_generated_rubric(
        rubric,
        question_id,
        question_type,
        answer_spec,
        rules,
    )
    return rubric


def rubric_from_authored_answer_parts(
    question_id: str,
    question_type: QuestionType | None,
    answer_spec: AnswerSpec,
    prompt_version: str,
) -> GeneratedQuestionRubric | None:
    """Build stable multipart components from the existing authored contract."""

    explanation_components: dict[
        QuestionType,
        tuple[tuple[str, str], tuple[str, str]],
    ] = {
        "CHOICE_WITH_EXPLANATION": (
            ("ANSWER_SELECTION", "Selects the correct option or answer value."),
            (
                "ANSWER_EXPLANATION",
                "Explains why the selected answer satisfies the question.",
            ),
        ),
        "TRUE_FALSE_WITH_EXPLANATION": (
            ("ANSWER_SELECTION", "States the correct true-or-false judgement."),
            (
                "ANSWER_EXPLANATION",
                "Explains why the stated judgement satisfies the question.",
            ),
        ),
    }
    explanation_parts = explanation_components.get(question_type)
    if explanation_parts is not None:
        cache_source = json.dumps(
            {
                "question_id": question_id,
                "question_type": question_type,
                "answer_spec_id": answer_spec.answer_spec_id,
                "prompt_version": prompt_version,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return GeneratedQuestionRubric(
            question_id=question_id,
            required_concepts=[
                GeneratedConcept(
                    concept_id=component_id,
                    description=description,
                    required=True,
                )
                for component_id, description in explanation_parts
            ],
            completion_rule="ALL_REQUIRED_CONCEPTS",
            cache_key=hashlib.sha256(cache_source.encode("utf-8")).hexdigest(),
            prompt_version=prompt_version,
        )

    if question_type != "MULTI_PART_SHORT_RESPONSE":
        return None
    # Older authored contracts sometimes store the operator together with the
    # fixed value (for example, "m; +7").  The expression itself is reliable
    # evidence that these are three distinct semantic roles.
    raw_answer_parts = [part.strip() for part in answer_spec.canonical_answer.split(";")]
    expression = _expression_parts(answer_spec.canonical_answer.replace(";", " "))
    if (
        expression is not None
        and len(raw_answer_parts) == 2
        and re.fullmatch(r"[+\-×x*]\s*\d+", raw_answer_parts[1]) is not None
    ):
        role_parts = (
            ("CHANGING_VALUE", "The variable or starting value changes."),
            ("FIXED_VALUE", "The numerical value that stays fixed."),
            ("OPERATION", "The operation represented by the sign."),
        )
        cache_source = json.dumps(
            {"question_id": question_id, "roles": role_parts, "prompt_version": prompt_version},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return GeneratedQuestionRubric(
            question_id=question_id,
            required_concepts=[
                GeneratedConcept(concept_id=concept_id, description=description, required=True)
                for concept_id, description in role_parts
            ],
            completion_rule="ALL_REQUIRED_CONCEPTS",
            cache_key=hashlib.sha256(cache_source.encode("utf-8")).hexdigest(),
            prompt_version=prompt_version,
        )
    answer_parts = [
        part.strip()
        for part in answer_spec.canonical_answer.split(";")
        if part.strip()
    ]
    if len(answer_parts) < 2:
        return None
    cache_source = json.dumps(
        {
            "question_id": question_id,
            "answer_parts": answer_parts,
            "prompt_version": prompt_version,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return GeneratedQuestionRubric(
        question_id=question_id,
        required_concepts=[
            GeneratedConcept(
                concept_id=f"REQUIRED_COMPONENT_{index}",
                description=answer_part,
                required=True,
            )
            for index, answer_part in enumerate(answer_parts, start=1)
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key=hashlib.sha256(cache_source.encode("utf-8")).hexdigest(),
        prompt_version=prompt_version,
    )


def expression_role_rubric_from_question(
    question_id: str,
    question_type: QuestionType | None,
    question: str,
    answer_spec: AnswerSpec,
    prompt_version: str,
) -> GeneratedQuestionRubric | None:
    """Require all expression roles when an authored prompt asks for them."""

    if question_type != "MULTI_PART_SHORT_RESPONSE":
        return None
    if re.fullmatch(r"\s*[a-z]\s*[+\-×x*]\s*\d+\s*", answer_spec.canonical_answer.casefold()) is None:
        return None
    normalized_question = question.casefold()
    asks_changing_value = "chang" in normalized_question
    asks_fixed_value = "fixed" in normalized_question or "stays the same" in normalized_question
    if not (asks_changing_value and asks_fixed_value):
        return None

    role_parts: list[tuple[str, str]] = []
    if "general rule" in normalized_question or "write the rule" in normalized_question:
        role_parts.append(("GENERAL_RULE", "States the general rule."))
    role_parts.extend(
        [
            ("CHANGING_VALUE", "The variable or starting value changes."),
            ("FIXED_VALUE", "The numerical value that stays fixed."),
        ]
    )
    if "operation" in normalized_question:
        role_parts.append(("OPERATION", "The operation represented by the sign."))
    cache_source = json.dumps(
        {
            "question_id": question_id,
            "question": normalized_question,
            "roles": role_parts,
            "prompt_version": prompt_version,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return GeneratedQuestionRubric(
        question_id=question_id,
        required_concepts=[
            GeneratedConcept(concept_id=concept_id, description=description, required=True)
            for concept_id, description in role_parts
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key=hashlib.sha256(cache_source.encode("utf-8")).hexdigest(),
        prompt_version=prompt_version,
    )


def objective_for_rubric(
    objective: ActiveTeachingObjective | None,
    rubric: GeneratedQuestionRubric,
) -> ActiveTeachingObjective:
    """Keep persisted evidence only when it belongs to the current rubric."""

    if objective is None:
        return initial_guided_objective(rubric)
    required_ids = {
        concept.concept_id
        for concept in rubric.required_concepts
        if concept.required
    }
    objective_ids = {
        *objective.confirmed_concept_ids,
        *objective.missing_concept_ids,
    }
    if objective_ids != required_ids:
        return initial_guided_objective(rubric)
    return objective


def objective_with_persisted_choice_selection(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> ActiveTeachingObjective:
    """Preserve a valid selected choice while the learner explains it."""

    if request.question_type not in {
        "CHOICE_WITH_EXPLANATION",
        "TRUE_FALSE_WITH_EXPLANATION",
    }:
        return objective
    selected_option_id = (
        typed_choice_selection(request)
        or (
            request.guided_teaching_state.selected_option_id
            if request.guided_teaching_state is not None
            and request.guided_teaching_state.question_id == request.question_id
            else None
        )
    )
    answer_spec = request.answer_spec
    if selected_option_id is None or answer_spec is None:
        return objective
    accepted_choices = {
        normalized_choice_response(answer)
        for answer in [answer_spec.canonical_answer, *answer_spec.accepted_answers]
    }
    selected_option_text = (
        request.guided_teaching_state.selected_option_text
        if request.guided_teaching_state is not None
        and request.guided_teaching_state.question_id == request.question_id
        else None
    )
    selected_choice_is_correct = (
        normalized_choice_response(selected_option_id) in accepted_choices
        or (
            selected_option_text is not None
            and normalized_choice_response(selected_option_text) in accepted_choices
        )
    )
    if not selected_choice_is_correct:
        return objective
    required_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if component.required
    }
    if "ANSWER_SELECTION" not in required_ids:
        return objective
    confirmed_ids = set(objective.confirmed_concept_ids)
    confirmed_ids.add("ANSWER_SELECTION")
    missing_ids = required_ids - confirmed_ids
    return ActiveTeachingObjective(
        objective_type="EXPLAIN_REASONING",
        target_concept_ids=sorted(missing_ids),
        confirmed_concept_ids=sorted(confirmed_ids),
        missing_concept_ids=sorted(missing_ids),
    )


def objective_with_persisted_component_evidence(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> ActiveTeachingObjective:
    """Recover confirmed guided components from the durable session state."""

    state = request.guided_teaching_state
    if state is None or state.question_id != request.question_id:
        return objective
    required_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if component.required
    }
    confirmed_ids = (
        set(objective.confirmed_concept_ids)
        | set(state.confirmed_component_ids)
    ) & required_ids
    missing_ids = required_ids - confirmed_ids
    if (
        confirmed_ids == set(objective.confirmed_concept_ids)
        and missing_ids == set(objective.missing_concept_ids)
    ):
        return objective
    return ActiveTeachingObjective(
        objective_type=objective.objective_type,
        target_concept_ids=sorted(missing_ids),
        confirmed_concept_ids=sorted(confirmed_ids),
        missing_concept_ids=sorted(missing_ids),
    )


def focused_unresolved_prompt(
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    default_message: str,
) -> str:
    """Ask for the first missing requirement without disclosing its answer."""

    missing_ids = set(objective.missing_concept_ids)
    missing_component = next(
        (
            component
            for component in rubric.required_concepts
            if component.required and component.concept_id in missing_ids
        ),
        None,
    )
    if missing_component is None:
        return default_message
    component_kind = (
        f"{missing_component.concept_id} {missing_component.description}"
    ).casefold()
    if any(term in component_kind for term in ("explanation", "explain", "reason", "why")):
        return "What mathematical reason shows that this choice works for every starting value?"
    if any(term in component_kind for term in ("changing", "changes", "variable")):
        return "Which value can change from one example to another?"
    if any(term in component_kind for term in ("fixed", "increment", "constant")):
        return "What operation or amount stays fixed?"
    if any(term in component_kind for term in ("general_rule", "general rule", "expression")):
        return "What general rule represents this situation?"
    if re.search(
        r"\b[a-z]\s*(?:[+\-*/]|add|subtract|multiply|divide)\s*\d+\b",
        component_kind,
    ):
        return "What general rule represents this situation?"
    if any(term in component_kind for term in ("expanded", "repeated", "adjacent")):
        return "What do the letters represent when the expression is expanded?"
    if any(term in component_kind for term in ("choice", "selection", "option")):
        return "Which option represents every possible starting value?"
    return "State the remaining idea in your own words."


def active_component_id(
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective | None,
) -> str | None:
    """Return the first authored unresolved component in its authored order."""

    if objective is None:
        return None
    missing_ids = set(objective.missing_concept_ids)
    return next(
        (
            component.concept_id
            for component in rubric.required_concepts
            if component.required and component.concept_id in missing_ids
        ),
        None,
    )


def prompt_type_for_message(message: str) -> GuidedPromptType:
    """Classify only controller-owned prompts; prose is not state."""

    normalized = message.casefold()
    if "can one fixed starting number describe every possible case" in normalized:
        return "OPTION_COMPARISON"
    if normalized.startswith("check the example") or normalized.startswith(
        "check the last example"
    ):
        return "SOURCE_CORRECTION"
    if "different starting value" in normalized or "same rule predict" in normalized:
        return "DEFENCE"
    return "COMPONENT"


@dataclass(frozen=True)
class TeachingStep:
    """One deterministic question in a guided algebra conversation."""

    step_id: str
    prompt: str


def _expression_parts(text: str) -> tuple[str, str, str] | None:
    match = re.search(r"\b([a-z])\s*([+\-×x*])\s*(\d+)\b", text.casefold())
    if match is None:
        return None
    return match.group(1), match.group(2), match.group(3)


def requires_written_symbolic_rule_evidence(
    request: ClassificationRequest,
    student_state: GuidedStudentState,
) -> bool:
    """Keep an algebra rule open until reliable canvas maths confirms it."""

    if student_state != "CORRECT":
        return False
    if request.question_type != "SHORT_RESPONSE":
        return False
    if request.answer_spec is None:
        return False
    # A canvas-write request confirms a rule that has already been evaluated as
    # correct. Never let an optimistic model state turn a contradictory typed
    # expression into a request to write that expression on the canvas.
    if evaluate_answer_contract(request) == "INCORRECT":
        return False
    if _expression_parts(request.answer_spec.canonical_answer) is None:
        return False
    return request.canvas_solution_complete_candidate is False


def teaching_steps_for(request: ClassificationRequest) -> list[TeachingStep]:
    """Build a small, predictable plan from the authored question contract."""

    answer_text = request.answer_spec.canonical_answer if request.answer_spec else ""
    if (
        _expression_parts(answer_text) or _expression_parts(request.question)
    ) is None:
        return []
    question = request.question.casefold()
    changing_prompt = "Which part can take different possible values?"
    fixed_prompt = "Which value stays fixed in this rule?"
    operation_prompt = "What operation does the sign tell us to use?"
    rule_prompt = "What general rule represents this situation?"
    requires_operation_step = "operation" in question
    requires_role_identification = any(
        phrase in question
        for phrase in (
            "identify the changing",
            "identify what changes",
            "state what changes",
            "what changes and what stays fixed",
            "what changes and stays fixed",
            "fixed value",
            "which value stays fixed",
        )
    )
    requires_defence = any(
        phrase in question
        for phrase in (
            "explain why",
            "explain briefly",
            "why does",
            "works for every",
            "works in every",
            "justify",
        )
    )
    if "general rule" in question and requires_role_identification:
        steps = [
            TeachingStep("GENERAL_RULE", rule_prompt),
            TeachingStep("CHANGING_VALUE", changing_prompt),
            TeachingStep("FIXED_VALUE", fixed_prompt),
        ]
        if requires_operation_step:
            steps.append(TeachingStep("OPERATION", operation_prompt))
        return steps
    if "general rule" in question:
        steps = [TeachingStep("GENERAL_RULE", rule_prompt)]
        if requires_defence:
            steps.append(
                TeachingStep(
                    "DEFENCE",
                    "Try a different starting value: what does the same rule predict?",
                )
            )
        return steps
    if all(term in question for term in ("changing", "fixed")):
        steps = [
            TeachingStep("CHANGING_VALUE", changing_prompt),
            TeachingStep("FIXED_VALUE", fixed_prompt),
        ]
        if requires_operation_step:
            steps.append(TeachingStep("OPERATION", operation_prompt))
        return steps
    if any(
        phrase in question
        for phrase in ("general rule", "new-score rule", "new score rule", "write the rule")
    ):
        return [TeachingStep("GENERAL_RULE", rule_prompt)]
    return []


def answer_step_ids_for(request: ClassificationRequest) -> list[str]:
    """Derive stable learner-step IDs from the authored answer contract."""

    answer_spec = request.answer_spec
    if answer_spec is None:
        return []
    return [
        f"{answer_spec.answer_spec_id}:STEP:{index}"
        for index, _step in enumerate(answer_spec.answer_steps, start=1)
    ]


def teaching_step_from_message(message: str, steps: list[TeachingStep]) -> str | None:
    """Recover the exact pending step from a controller-owned prompt."""

    normalized = message.casefold()
    for step in steps:
        if step.prompt.casefold() in normalized:
            return step.step_id
    if "replace the changing starting number with a letter" in normalized:
        return "GENERAL_RULE"
    return None


def active_teaching_step(request: ClassificationRequest) -> TeachingStep | None:
    """Return the persisted step, or initialise it from the question once."""

    steps = teaching_steps_for(request)
    if not steps:
        return None
    persisted = request.guided_teaching_state
    if persisted is not None and persisted.question_id == request.question_id:
        if persisted.current_step_index is not None:
            if persisted.current_step_index >= len(steps):
                raise ValueError(
                    "guided current_step_index is outside the authored teaching plan; "
                    f"question_id={request.question_id!r}, "
                    f"current_step_index={persisted.current_step_index}, "
                    f"step_count={len(steps)}"
                )
            return steps[persisted.current_step_index]
        active_id = persisted.active_step_id
        if active_id is not None:
            return next((step for step in steps if step.step_id == active_id), steps[0])
    return steps[0]


def _component_for_step(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    step_id: str,
) -> str | None:
    if step_id == "DEFENCE":
        return None
    terms = {
        "GENERAL_RULE": ("general", "rule", "expression"),
        "CHANGING_VALUE": ("changing", "changes", "variable", "starting"),
        "FIXED_VALUE": ("fixed", "constant", "increment"),
        "OPERATION": ("operation", "add", "addition", "plus", "multiply"),
    }[step_id]
    matched_component = next(
        (
            component.concept_id
            for component in rubric.required_concepts
            if component.required
            and any(term in f"{component.concept_id} {component.description}".casefold() for term in terms)
        ),
        None,
    )
    if matched_component is not None:
        return matched_component
    generic_components = [
        component.concept_id
        for component in rubric.required_concepts
        if component.required and component.concept_id.startswith("REQUIRED_COMPONENT_")
    ]
    teaching_steps = teaching_steps_for(request)
    generic_index = next(
        (
            index
            for index, teaching_step in enumerate(teaching_steps)
            if teaching_step.step_id == step_id
        ),
        None,
    )
    if generic_index is None:
        return None
    return (
        generic_components[generic_index]
        if generic_index < len(generic_components)
        else None
    )


def evidence_source_for_request(request: ClassificationRequest) -> GuidedEvidenceSource:
    """Map transport input to the durable evidence source contract."""

    return {
        "TEXT": "TEXT",
        "VOICE": "VOICE",
        "CANVAS": "CANVAS",
        "CHOICE": "STRUCTURED",
        "MIXED": "STRUCTURED",
    }[request.input_source]


def operation_with_fixed_value_mentioned(
    normalized_student_input: str,
    operator: str,
    fixed_value: str,
) -> bool:
    """Recognize a phrase such as "add 4" as the fixed amount and operation."""

    operation_words = {
        "+": ("add", "plus"),
        "-": ("subtract", "minus"),
        "×": ("multiply", "multiplication", "times"),
        "x": ("multiply", "multiplication", "times"),
        "*": ("multiply", "multiplication", "times"),
        "÷": ("divide", "division"),
        "/": ("divide", "division"),
    }.get(operator, ())
    return any(
        re.search(
            rf"\b{re.escape(word)}\s+{re.escape(fixed_value)}\b",
            normalized_student_input,
        )
        is not None
        for word in operation_words
    )


def deterministic_turn_evidence(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    rules: ClassifierRulesConfig,
) -> list[GuidedEvidenceClaim]:
    """Extract clear current-turn algebra evidence without reopening past steps."""

    expression = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    if expression is None:
        return []
    variable, operator, fixed_value = expression
    normalized = re.sub(r"\s+", " ", request.student_input.casefold()).strip()
    compact = re.sub(r"\s+", "", normalized)
    source = evidence_source_for_request(request)
    active_step = active_teaching_step(request)
    contradiction = active_role_contradiction(request)
    claims: list[GuidedEvidenceClaim] = []

    def add_claim(
        step_id: str,
        status: Literal["DEMONSTRATED", "CONTRADICTED"],
        evidence_source: GuidedEvidenceSource,
    ) -> None:
        component_id = _component_for_step(request, rubric, step_id) or step_id
        claim = GuidedEvidenceClaim(
            concept_id=component_id,
            status=status,
            source=evidence_source,
        )
        if claim not in claims:
            claims.append(claim)

    if contradiction is not None:
        add_claim(
            {
                "VARIABLE_CALLED_FIXED": "CHANGING_VALUE",
                "FIXED_VALUE_CALLED_CHANGING": "FIXED_VALUE",
                "OPERATION_CALLED_VALUE": "OPERATION",
            }[contradiction],
            "CONTRADICTED",
            source,
        )
        return claims

    if re.fullmatch(rf"{re.escape(variable)}\s*{re.escape(operator)}\s*{fixed_value}", compact):
        add_claim("GENERAL_RULE", "DEMONSTRATED", source)
    if (
        variable in normalized
        and any(marker in normalized for marker in ("change", "changing", "varies", "variable", "any", "different"))
    ) or (
        active_step is not None
        and active_step.step_id == "CHANGING_VALUE"
        and normalized == variable
    ):
        add_claim("CHANGING_VALUE", "DEMONSTRATED", source)
    fixed_value_identified = (
        fixed_value in normalized
        and any(
            marker in normalized
            for marker in ("fixed", "constant", "stays", "same", "remains")
        )
    ) or operation_with_fixed_value_mentioned(normalized, operator, fixed_value)
    if fixed_value_identified:
        add_claim("FIXED_VALUE", "DEMONSTRATED", source)
    operation_words = (
        ("add", "addition", "plus")
        if operator == "+"
        else ("subtract", "subtraction", "minus")
    )
    if any(word in normalized for word in operation_words) or has_reliable_canvas_operator_evidence(
        request,
        operator,
        rules,
    ):
        add_claim("OPERATION", "DEMONSTRATED", source)
    canvas_text = " ".join(
        [
            request.canvas_ocr_text or "",
            *[
                region.text
                for region in request.canvas_regions
                if region.confidence >= rules.guided_learning.minimum_ocr_confidence
            ],
        ]
    ).casefold()
    if canvas_text:
        if variable in canvas_text and any(
            marker in canvas_text
            for marker in ("change", "changing", "varies", "variable", "any", "different")
        ):
            add_claim("CHANGING_VALUE", "DEMONSTRATED", "OCR")
        if fixed_value in canvas_text and any(
            marker in canvas_text
            for marker in ("fixed", "constant", "stays", "same", "remains")
        ):
            add_claim("FIXED_VALUE", "DEMONSTRATED", "OCR")
        if any(word in canvas_text for word in operation_words):
            add_claim("OPERATION", "DEMONSTRATED", "OCR")
    selected_option = typed_choice_selection(request)
    if selected_option is not None and request.answer_spec is not None:
        accepted_choices = {
            normalized_choice_response(answer)
            for answer in [
                request.answer_spec.canonical_answer,
                *request.answer_spec.accepted_answers,
            ]
        }
        if normalized_choice_response(selected_option) in accepted_choices:
            claims.append(
                GuidedEvidenceClaim(
                    concept_id="ANSWER_SELECTION",
                    status="DEMONSTRATED",
                    source="STRUCTURED",
                )
            )
    return claims


def objective_with_turn_evidence(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> ActiveTeachingObjective:
    """Merge clear current evidence before choosing the next tutor prompt."""

    claims = deterministic_turn_evidence(request, rubric, rules)
    contradicted = {
        claim.concept_id for claim in claims if claim.status == "CONTRADICTED"
    }
    demonstrated = {
        claim.concept_id for claim in claims if claim.status == "DEMONSTRATED"
    }
    confirmed = set(objective.confirmed_concept_ids)
    confirmed.difference_update(contradicted)
    required = {
        concept.concept_id
        for concept in rubric.required_concepts
        if concept.required
    }
    confirmed.update(demonstrated & required)
    if request.question_type == "CHOICE_WITH_EXPLANATION" and "ANSWER_SELECTION" in confirmed:
        historical_claims = (
            request.guided_teaching_state.evidence_ledger
            if request.guided_teaching_state is not None
            else []
        )
        demonstrated_roles = {
            claim.concept_id
            for claim in [*historical_claims, *claims]
            if claim.status == "DEMONSTRATED"
        }
        if (
            {"CHANGING_VALUE", "FIXED_VALUE"}.issubset(demonstrated_roles)
            and "ANSWER_EXPLANATION" in required
        ):
            confirmed.add("ANSWER_EXPLANATION")
    missing = required - confirmed
    return ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION" if not missing else "EXPLAIN_CONCEPT",
        target_concept_ids=sorted(missing),
        confirmed_concept_ids=sorted(confirmed),
        missing_concept_ids=sorted(missing),
    )


def completed_evidence_evaluation(
    objective: ActiveTeachingObjective,
) -> GuidedEvaluation | None:
    """Finish a question before wording can reopen a completed concept."""

    if objective.missing_concept_ids:
        return None
    return GuidedEvaluation(
        student_state="CORRECT",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=1.0,
        next_objective=None,
        tutor_message="Nice work.",
        tutor_message_voice="Nice work.",
    )


def _controller_objective_after(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rubric: GeneratedQuestionRubric,
    confirmed_step_id: str | None,
) -> ActiveTeachingObjective:
    confirmed = set(objective.confirmed_concept_ids)
    if confirmed_step_id is not None:
        component_id = _component_for_step(request, rubric, confirmed_step_id)
        if component_id is not None:
            confirmed.add(component_id)
    required = {
        component.concept_id for component in rubric.required_concepts if component.required
    }
    return ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=sorted(required - confirmed),
        confirmed_concept_ids=sorted(confirmed),
        missing_concept_ids=sorted(required - confirmed),
    )


def _controller_evaluation(
    request: ClassificationRequest,
    state: GuidedStudentState,
    objective: ActiveTeachingObjective,
    message: str,
    confirmed_step_id: str | None,
    rubric: GeneratedQuestionRubric,
) -> GuidedEvaluation:
    next_objective = _controller_objective_after(
        request,
        objective,
        rubric,
        confirmed_step_id,
    )
    newly_confirmed = []
    if confirmed_step_id is not None:
        component_id = _component_for_step(request, rubric, confirmed_step_id)
        if component_id is not None and component_id not in objective.confirmed_concept_ids:
            newly_confirmed = [component_id]
    return GuidedEvaluation(
        student_state=state,
        newly_confirmed_concept_ids=newly_confirmed,
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=next_objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=next_objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def _describes_changing_starting_value(student_input: str) -> bool:
    """Return whether a response identifies that the starting value varies."""

    normalized = re.sub(r"\s+", " ", student_input.casefold()).strip()
    describes_change = any(
        marker in normalized for marker in ("change", "vary", "different")
    )
    describes_start = any(marker in normalized for marker in ("starting", "first"))
    describes_value = any(marker in normalized for marker in ("number", "value"))
    numeric_values = re.findall(r"\b\d+\b", normalized)
    return describes_change and (
        (describes_start and describes_value) or len(set(numeric_values)) >= 2
    )


def active_role_contradiction(request: ClassificationRequest) -> str | None:
    """Identify a role claim that contradicts the expression being discussed."""

    active_step = active_teaching_step(request)
    expression = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    if active_step is None or expression is None:
        return None
    variable, operator, fixed_value = expression
    normalized = re.sub(r"\s+", " ", request.student_input.casefold()).strip()
    if re.search(
        rf"\b{re.escape(variable)}\b\s+(?:is|stays|remains)\s+"
        r"(?:fixed|constant)\b",
        normalized,
    ):
        return "VARIABLE_CALLED_FIXED"
    if re.search(
        rf"(?<!\d){re.escape(fixed_value)}(?!\d)\s+"
        r"(?:changes|change|varies|vary)\b",
        normalized,
    ):
        return "FIXED_VALUE_CALLED_CHANGING"
    if (
        f"{operator} is fixed" in normalized
        or f"{operator} is a value" in normalized
        or "plus is fixed" in normalized
        or "plus is a value" in normalized
    ):
        return "OPERATION_CALLED_VALUE"
    return None


def role_contradiction_prompt(
    focus: str,
    rules: ClassifierRulesConfig,
) -> str:
    """Return the authored Socratic fallback for one role contradiction."""

    prompts = {
        "VARIABLE_CALLED_FIXED": (
            rules.guided_learning.critical_thinking.variable_called_fixed_prompt
        ),
        "FIXED_VALUE_CALLED_CHANGING": (
            rules.guided_learning.critical_thinking.fixed_value_called_changing_prompt
        ),
        "OPERATION_CALLED_VALUE": (
            rules.guided_learning.critical_thinking.operation_called_value_prompt
        ),
    }
    return prompts[focus]


def deterministic_teaching_step_evaluation(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Evaluate direct replies to the current algebra sub-question without an LLM."""

    step = active_teaching_step(request)
    expression = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    if step is None or expression is None:
        return None
    variable, operator, number = expression
    normalized = re.sub(r"\s+", " ", request.student_input.casefold()).strip()
    compact = re.sub(r"\s+", "", normalized)
    if normalized in {
        "idk",
        "i have no idea",
        "i do not understand",
        "i didn't understand",
        "i dont understand",
        "not sure",
        "what",
        "what?",
        "what do i state",
        "are u stupid",
    }:
        return None
    steps = teaching_steps_for(request)
    step_index = next(index for index, item in enumerate(steps) if item.step_id == step.step_id)
    next_step = steps[step_index + 1] if step_index + 1 < len(steps) else None

    contradiction = active_role_contradiction(request)
    if contradiction is not None:
        contradicted_step_id = {
            "VARIABLE_CALLED_FIXED": "CHANGING_VALUE",
            "FIXED_VALUE_CALLED_CHANGING": "FIXED_VALUE",
            "OPERATION_CALLED_VALUE": "OPERATION",
        }[contradiction]
        contradicted_component = _component_for_step(
            request,
            rubric,
            contradicted_step_id,
        )
        message = role_contradiction_prompt(contradiction, rules)
        return GuidedEvaluation(
            student_state="WRONG",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=(
                [contradicted_component]
                if contradicted_component is not None
                else []
            ),
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=message,
            tutor_message_voice=message,
        )
    if (
        step.step_id == "CHANGING_VALUE"
        and any(word in normalized for word in ("add", "addition", "plus"))
        and not (
            variable in normalized
            and any(marker in normalized for marker in ("change", "changing", "varies", "variable"))
        )
        and not (
            number in normalized
            and any(marker in normalized for marker in ("fixed", "stays", "constant", "same"))
        )
    ):
        message = rules.guided_learning.critical_thinking.active_role_before_operation_prompt
        return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)

    # A learner can answer several roles in one sentence.  Preserve each
    # demonstrated role, but do not accept an operation as if it were a value.
    if step.step_id in {"CHANGING_VALUE", "FIXED_VALUE", "OPERATION"}:
        changing_claimed = variable in normalized and any(
            marker in normalized for marker in ("change", "changing", "varies", "variable")
        )
        fixed_claimed = (
            number in normalized
            and any(
                marker in normalized for marker in ("fixed", "stays", "constant", "same")
            )
        ) or operation_with_fixed_value_mentioned(normalized, operator, number)
        operation_called_value = (
            any(token in normalized for token in ("+ is", "plus is", "the +", "the plus"))
            and any(token in normalized for token in ("fixed value", "a value", "stays fixed"))
        )
        operation_identified_on_canvas = has_reliable_canvas_operator_evidence(
            request,
            operator,
            rules,
        )
        operation_identified_in_response = (
            not operation_called_value
            and any(
                word in normalized
                for word in (
                    ("add", "addition", "plus")
                    if operator == "+"
                    else ("subtract", "subtraction", "minus")
                )
            )
        )
        operation_identified = (
            operation_identified_on_canvas or operation_identified_in_response
        )
        logger.info(
            "guided_role_evidence_evaluated",
            extra={
                "question_id": request.question_id,
                "active_step_id": step.step_id,
                "changing_claimed": changing_claimed,
                "fixed_claimed": fixed_claimed,
                "operation_identified_on_canvas": operation_identified_on_canvas,
                "operation_identified_in_response": operation_identified_in_response,
                "canvas_region_texts": [
                    region.text
                    for region in request.canvas_regions
                    if region.confidence
                    >= rules.guided_learning.minimum_ocr_confidence
                ],
                "canvas_ocr_text": request.canvas_ocr_text,
                "component_ids_by_step": {
                    teaching_step.step_id: _component_for_step(
                        request,
                        rubric,
                        teaching_step.step_id,
                    )
                    for teaching_step in teaching_steps_for(request)
                },
            },
        )
        if changing_claimed and fixed_claimed and operation_identified:
            confirmed = set(objective.confirmed_concept_ids)
            for role in ("CHANGING_VALUE", "FIXED_VALUE", "OPERATION"):
                component_id = _component_for_step(request, rubric, role)
                if component_id is not None:
                    confirmed.add(component_id)
            missing = [
                item
                for item in rubric.required_concepts
                if item.required and item.concept_id not in confirmed
            ]
            next_objective = ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=[item.concept_id for item in missing],
                confirmed_concept_ids=sorted(confirmed),
                missing_concept_ids=[item.concept_id for item in missing],
            )
            message = (
                f"You identified {variable} as changing, {number} as fixed, "
                f"and {operator} as the operation. Nice work."
            )
            return GuidedEvaluation(
                student_state="CORRECT" if not missing else "PARTIAL",
                newly_confirmed_concept_ids=sorted(
                    confirmed - set(objective.confirmed_concept_ids)
                ),
                preserved_concept_ids=objective.confirmed_concept_ids,
                contradicted_concept_ids=[],
                missing_concept_ids=next_objective.missing_concept_ids,
                selected_error_code=None,
                confidence=1.0,
                next_objective=next_objective,
                tutor_message=message,
                tutor_message_voice=message,
            )
        if changing_claimed and fixed_claimed and operation_called_value:
            confirmed = set(objective.confirmed_concept_ids)
            for role in ("CHANGING_VALUE", "FIXED_VALUE"):
                component_id = _component_for_step(request, rubric, role)
                if component_id is not None:
                    confirmed.add(component_id)
            operation_id = _component_for_step(request, rubric, "OPERATION")
            missing = [item for item in rubric.required_concepts if item.required and item.concept_id not in confirmed]
            next_objective = ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=[item.concept_id for item in missing],
                confirmed_concept_ids=sorted(confirmed),
                missing_concept_ids=[item.concept_id for item in missing],
            )
            message = (
                f"You correctly identified {variable} as changing and {number} as fixed. "
                f"Is {operator} a value, or does it tell us what to do?"
            )
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=sorted(confirmed - set(objective.confirmed_concept_ids)),
                preserved_concept_ids=objective.confirmed_concept_ids,
                contradicted_concept_ids=[operation_id] if operation_id is not None else [],
                missing_concept_ids=next_objective.missing_concept_ids,
                selected_error_code=None,
                confidence=1.0,
                next_objective=next_objective,
                tutor_message=message,
                tutor_message_voice=message,
            )
        if changing_claimed and fixed_claimed:
            confirmed = set(objective.confirmed_concept_ids)
            for role in ("CHANGING_VALUE", "FIXED_VALUE"):
                component_id = _component_for_step(request, rubric, role)
                if component_id is not None:
                    confirmed.add(component_id)
            missing = [
                item
                for item in rubric.required_concepts
                if item.required and item.concept_id not in confirmed
            ]
            next_objective = ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=[item.concept_id for item in missing],
                confirmed_concept_ids=sorted(confirmed),
                missing_concept_ids=[item.concept_id for item in missing],
            )
            message = (
                f"You correctly identified {variable} as changing and {number} as fixed. "
                f"What operation does {operator} tell us to use?"
            )
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=sorted(
                    confirmed - set(objective.confirmed_concept_ids)
                ),
                preserved_concept_ids=objective.confirmed_concept_ids,
                contradicted_concept_ids=[],
                missing_concept_ids=next_objective.missing_concept_ids,
                selected_error_code=None,
                confidence=1.0,
                next_objective=next_objective,
                tutor_message=message,
                tutor_message_voice=message,
            )

    if operator == "+" and any(
        word in normalized for word in ("minus", "subtract", "subtraction")
    ):
        message = rules.guided_learning.critical_thinking.operation_direction_mismatch_prompt
        return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
    if operator == "-" and any(
        word in normalized for word in ("plus", "add", "addition")
    ):
        message = rules.guided_learning.critical_thinking.operation_direction_mismatch_prompt
        return _controller_evaluation(request, "WRONG", objective, message, None, rubric)

    if step.step_id == "GENERAL_RULE":
        if re.fullmatch(rf"{re.escape(variable)}\s*{re.escape(operator)}\s*{number}", compact):
            if next_step is None:
                return _controller_evaluation(request, "CORRECT", objective, "Nice work.", step.step_id, rubric)
            message = f"Good. {next_step.prompt}"
            return _controller_evaluation(request, "PARTIAL", objective, message, step.step_id, rubric)
        if len(steps) == 1 and any(
            word in normalized
            for word in (
                ("add", "addition", "plus")
                if operator == "+"
                else ("subtract", "subtraction", "minus")
            )
        ):
            message = rules.guided_learning.critical_thinking.wrong_direct_rule_prompt
            return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)
        if len(steps) == 1 and number in normalized and any(
            marker in normalized for marker in ("fixed", "constant", "stays", "same", "remains")
        ):
            message = (
                "Yes, that number stays fixed. Use the letter for the starting "
                "number and write the full rule."
            )
            return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)
        if len(steps) == 1 and normalized in {
            "idk",
            "i dont know",
            "i don't know",
            "i dont know what you mean",
            "i don't know what you mean",
            "i dont know what u mean",
            "i don't know what u mean",
        }:
            message = rules.guided_learning.critical_thinking.wrong_direct_rule_prompt
            return _controller_evaluation(request, "STUCK", objective, message, None, rubric)
        typed_rule = re.fullmatch(
            r"\s*(?:(?:it'?s|it is|the rule is)\s*)?[a-z]\s*[+\-×x*]\s*\d+\s*",
            normalized,
        )
        if typed_rule is not None:
            message = rules.guided_learning.critical_thinking.wrong_direct_rule_prompt
            return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
        if _numeric_expressions(request.student_input):
            changing = next((item for item in steps if item.step_id == "CHANGING_VALUE"), None)
            if changing is not None:
                message = f"A general rule works for every starting number. {changing.prompt}"
                return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)
        if _describes_changing_starting_value(request.student_input):
            message = (
                "Yes—the starting number changes. Replace it with a letter and keep "
                "the operation that stays the same."
            )
            return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)
        return None

    if step.step_id == "DEFENCE":
        examples = _numeric_expressions(request.student_input)
        if examples:
            return _controller_evaluation(
                request,
                "CORRECT",
                objective,
                "Good defence: you tested the rule with another starting value.",
                None,
                rubric,
            )
        message = rules.guided_learning.critical_thinking.single_case_defence_prompt
        return _controller_evaluation(request, "PARTIAL", objective, message, None, rubric)

    if step.step_id == "CHANGING_VALUE":
        exact_aliases = {
            variable,
            "the starting number",
            "starting number",
            "the starting value",
            "starting value",
            "the first number",
            "first number",
        }
        valid_variable_statement = variable in normalized and any(
            marker in normalized
            for marker in (
                "change",
                "changing",
                "vary",
                "varies",
                "variable",
                "different",
            )
        )
        if (
            normalized in exact_aliases
            or valid_variable_statement
            or _describes_changing_starting_value(request.student_input)
        ):
            question = request.question.casefold()
            if (
                "general rule" in question
                and f"use {variable}" in question
                and "stays fixed" not in question
            ):
                message = (
                    "Yes. Replace the changing starting number with a letter. "
                    "Keep the operation that stays the same."
                )
                return _controller_evaluation(
                    request, "PARTIAL", objective, message, None, rubric
                )
            if next_step is None:
                return _controller_evaluation(request, "CORRECT", objective, "Nice work.", step.step_id, rubric)
            if next_step.step_id == "GENERAL_RULE":
                message = "Yes. Replace the changing starting number with a letter. Keep the operation that stays the same."
            else:
                message = f"Yes. {next_step.prompt}"
            return _controller_evaluation(request, "PARTIAL", objective, message, step.step_id, rubric)
        if number in compact:
            message = (
                "Not quite: the changing quantity is the letter, not the fixed number. "
                f"{step.prompt}"
            )
            return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
        message = f"Focus on the changing part only. {step.prompt}"
        return _controller_evaluation(request, "UNCLEAR", objective, message, None, rubric)

    if step.step_id == "FIXED_VALUE":
        expected = f"{operator}{number}"
        supplied_opposite_sign = (
            operator == "+"
            and re.search(rf"(?:^|\\s)-\\s*{re.escape(number)}\\b", normalized) is not None
        ) or (
            operator == "-"
            and re.search(rf"(?:^|\\s)\\+\\s*{re.escape(number)}\\b", normalized) is not None
        )
        if supplied_opposite_sign:
            message = rules.guided_learning.critical_thinking.fixed_value_sign_mismatch_prompt
            return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
        short_fixed_answer = re.fullmatch(
            (
                rf"(?:it'?s|it is|the (?:number|value) is)\s*"
                rf"[+\-−]?\s*{re.escape(number)}"
            ),
            normalized,
        ) is not None
        if (
            compact in {number, expected}
            or short_fixed_answer
            or (
                number in normalized
                and any(word in normalized for word in ("fixed", "constant", "stays"))
            )
        ):
            if next_step is None:
                return _controller_evaluation(request, "CORRECT", objective, "Nice work.", step.step_id, rubric)
            message = f"Yes, {number} stays fixed. {next_step.prompt}"
            return _controller_evaluation(
                request,
                "PARTIAL",
                objective,
                message,
                step.step_id,
                rubric,
            )
        if variable in normalized:
            message = (
                f"{variable} can change; we are looking for the number that stays the same. "
                f"{step.prompt}"
            )
            return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
        return _controller_evaluation(
            request, "UNCLEAR", objective, f"Focus on the fixed value only. {step.prompt}", None, rubric
        )

    if step.step_id == "OPERATION":
        accepted = (
            ("add", "addition", "plus")
            if operator == "+"
            else ("subtract", "subtraction", "minus")
        )
        if (
            any(word in normalized for word in accepted)
            or has_reliable_canvas_operator_evidence(
                request,
                operator,
                rules,
            )
        ):
            if next_step is None:
                return _controller_evaluation(request, "CORRECT", objective, "Nice work.", step.step_id, rubric)
            return _controller_evaluation(request, "PARTIAL", objective, f"Yes. {next_step.prompt}", step.step_id, rubric)
        incorrect = ("multiplication", "multiply", "division", "divide") if operator == "+" else ()
        if any(word in normalized for word in incorrect):
            message = f"Not this time: the + sign means addition, not {next(word for word in incorrect if word in normalized)}. {step.prompt}"
            return _controller_evaluation(request, "WRONG", objective, message, None, rubric)
        return _controller_evaluation(
            request, "UNCLEAR", objective, f"Focus on the operation only. {step.prompt}", None, rubric
        )
    return None


def teaching_state_for(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective | None,
    tutor_message: str,
) -> GuidedTeachingState:
    """Create the durable controller state for the next learner turn."""

    required_ids = [
        component.concept_id
        for component in rubric.required_concepts
        if component.required
    ]
    confirmed_ids = objective.confirmed_concept_ids if objective is not None else required_ids
    missing_ids = objective.missing_concept_ids if objective is not None else []
    previous = request.guided_teaching_state
    teaching_steps = teaching_steps_for(request)
    confirmed_set = set(confirmed_ids)
    completed_step_ids: list[str] = []
    for step in teaching_steps:
        component_id = _component_for_step(request, rubric, step.step_id)
        if component_id is None or component_id not in confirmed_set:
            break
        completed_step_ids.append(step.step_id)
    current_step_index = (
        len(completed_step_ids)
        if len(completed_step_ids) < len(teaching_steps)
        else None
    )
    active_step_id = (
        teaching_steps[current_step_index].step_id
        if current_step_index is not None
        else None
    )
    previous_matches_question = (
        previous is not None
        and previous.question_id == (request.question_id or rubric.question_id)
    )
    demonstrated_reasoning_ids = (
        set(previous.demonstrated_reasoning_ids) if previous_matches_question else set()
    )
    general_rule_evidence = general_rule_explanation_evidence(request)
    if (
        request.question_type == "CHOICE_WITH_EXPLANATION"
        and "ANSWER_SELECTION" in confirmed_ids
        and general_rule_evidence is not None
    ):
        changing_identified, fixed_identified = general_rule_evidence
        if changing_identified:
            demonstrated_reasoning_ids.add("GENERAL_RULE_CHANGING_VALUE")
        if fixed_identified:
            demonstrated_reasoning_ids.add("GENERAL_RULE_FIXED_VALUE")
    typed_option_evidence = typed_option_text_evidence(request)
    message_normalized = tutor_message.casefold()
    affect_state: Literal["NORMAL", "DISTRESS", "FRUSTRATED", "GENTLE_RETURN"] = (
        "DISTRESS"
        if "you are not stupid" in message_normalized
        else "FRUSTRATED"
        if "feel frustrating" in message_normalized
        else "GENTLE_RETURN"
        if previous_matches_question and previous.affect_state == "DISTRESS"
        else "NORMAL"
    )
    selected_option_id = typed_choice_selection(request) or (
        previous.selected_option_id if previous_matches_question else None
    )
    selected_option_text = selected_option_text_for_choice(request, selected_option_id) or (
        previous.selected_option_text if previous_matches_question else None
    )
    last_turn_evidence = deterministic_turn_evidence(
        request,
        rubric,
        load_classifier_rules(),
    )
    ledger_by_component = {
        claim.concept_id: claim
        for claim in (previous.evidence_ledger if previous_matches_question else [])
    }
    for claim in last_turn_evidence:
        ledger_by_component[claim.concept_id] = claim
    return GuidedTeachingState(
        question_id=request.question_id or rubric.question_id,
        objective_component_ids=required_ids,
        confirmed_component_ids=confirmed_ids,
        missing_component_ids=missing_ids,
        active_component_id=active_component_id(rubric, objective),
        last_tutor_question_type=prompt_type_for_message(tutor_message),
        selected_option_id=selected_option_id,
        selected_option_text=selected_option_text,
        typed_option_id=(
            typed_option_evidence[0]
            if typed_option_evidence is not None
            else (
                previous.typed_option_id if previous_matches_question else None
            )
        ),
        typed_option_text=(
            typed_option_evidence[1]
            if typed_option_evidence is not None
            else (
                previous.typed_option_text if previous_matches_question else None
            )
        ),
        awaiting_response=objective is not None,
        active_step_id=active_step_id,
        teaching_step_ids=[step.step_id for step in teaching_steps],
        answer_step_ids=answer_step_ids_for(request),
        completed_step_ids=completed_step_ids,
        current_step_index=current_step_index,
        affect_state=affect_state,
        last_reasoning_probe=(
            tutor_message
            if tutor_message.rstrip().endswith("?")
            else (previous.last_reasoning_probe if previous_matches_question else None)
        ),
        demonstrated_reasoning_ids=sorted(demonstrated_reasoning_ids),
        evidence_ledger=sorted(
            ledger_by_component.values(),
            key=lambda claim: claim.concept_id,
        ),
        last_turn_evidence=last_turn_evidence,
    )


def typed_choice_selection(request: ClassificationRequest) -> str | None:
    """Return a choice ID from a short answer or an explained selection."""

    if request.question_type != "CHOICE_WITH_EXPLANATION":
        return None
    choice = normalized_choice_response(request.student_input)
    if len(choice) == 1 and choice.isalpha():
        return choice
    matches = re.findall(
        r"(?:^\s*|\b(?:option|choose|chose|selected)\s+)([a-d])\b",
        request.student_input.casefold(),
    )
    return matches[0].upper() if len(set(matches)) == 1 else None


def selected_option_text_for_choice(
    request: ClassificationRequest,
    selected_option_id: str | None,
) -> str | None:
    """Resolve the authored text for a spoken or typed option selection."""

    answer_spec = request.answer_spec
    if selected_option_id is None or answer_spec is None:
        return None
    canonical_option_id = normalized_choice_response(answer_spec.canonical_answer)
    if normalized_choice_response(selected_option_id) != canonical_option_id:
        return None
    option_texts = [
        accepted_answer
        for accepted_answer in answer_spec.accepted_answers
        if normalized_choice_response(accepted_answer) != canonical_option_id
    ]
    for option_text in option_texts:
        if _expression_parts(option_text) is not None:
            return option_text
    return option_texts[0] if option_texts else None


def typed_option_text_evidence(
    request: ClassificationRequest,
) -> tuple[str, str] | None:
    """Recognise exact option text without treating it as a click selection."""

    if request.question_type != "CHOICE_WITH_EXPLANATION" or request.answer_spec is None:
        return None
    option_id = normalized_choice_response(request.answer_spec.canonical_answer)
    if len(option_id) != 1 or not option_id.isalpha():
        return None
    attempted = normalize_semantic_answer(request.student_input)
    if attempted == "":
        return None
    for accepted in request.answer_spec.accepted_answers:
        normalized_accepted = normalize_semantic_answer(accepted)
        if (
            normalized_accepted != ""
            and normalized_accepted != option_id
            and attempted == normalized_accepted
        ):
            return option_id.upper(), accepted
    return None


def ambiguous_symbol_number_input(student_input: str) -> bool:
    """Keep unclear spaced notation out of misconception tracking."""

    normalized = student_input.casefold().strip()
    if re.fullmatch(r"[a-z]\s+\d+", normalized) is None:
        return False
    return not any(symbol in normalized for symbol in ("+", "-", "×", "*", "/"))


def request_with_reliable_canvas_evidence(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> ClassificationRequest:
    """Make reliable current-turn OCR available to the guided evidence controller."""

    reliable_text = [
        region.text.strip()
        for region in request.canvas_regions
        if region.confidence >= rules.guided_learning.minimum_ocr_confidence
        and region.text.strip()
    ]
    if (
        request.canvas_ocr_text is not None
        and request.canvas_ocr_confidence is not None
        and request.canvas_ocr_confidence >= rules.guided_learning.minimum_ocr_confidence
        and request.canvas_ocr_text.strip()
    ):
        reliable_text.append(request.canvas_ocr_text.strip())
    if not reliable_text:
        return request
    evidence_text = " ".join(reliable_text)
    normalized_input = normalize_semantic_answer(request.student_input)
    normalized_evidence = normalize_semantic_answer(evidence_text)
    if normalized_evidence in normalized_input:
        return request
    merged_input = " ".join(part for part in (request.student_input.strip(), evidence_text) if part)
    logger.info(
        "guided_canvas_evidence_merged",
        extra={
            "question_id": request.question_id,
            "region_count": len(reliable_text),
        },
    )
    return request.model_copy(update={"student_input": merged_input})


def has_reliable_canvas_operator_evidence(
    request: ClassificationRequest,
    operator: str,
    rules: ClassifierRulesConfig,
) -> bool:
    """Return whether OCR isolated the operation symbol as student work."""

    if any(
        region.confidence >= rules.guided_learning.minimum_ocr_confidence
        and region.text.strip() == operator
        for region in request.canvas_regions
    ):
        return True
    if (
        request.canvas_ocr_text is None
        or request.canvas_ocr_confidence is None
        or request.canvas_ocr_confidence < rules.guided_learning.minimum_ocr_confidence
    ):
        return False
    return any(
        line.strip() == operator
        for line in request.canvas_ocr_text.splitlines()
    )


def wrong_choice_evaluation(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Challenge a definite wrong option before asking for an explanation."""

    if request.question_type != "CHOICE_WITH_EXPLANATION" or request.answer_spec is None:
        return None
    selected = typed_choice_selection(request)
    if selected is None:
        return None
    accepted = {
        normalized_choice_response(answer)
        for answer in [request.answer_spec.canonical_answer, *request.answer_spec.accepted_answers]
    }
    if selected in accepted:
        return None
    message = rules.guided_learning.critical_thinking.wrong_choice_prompt
    return GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=["ANSWER_SELECTION"],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def correct_choice_selection_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Move a spoken correct choice out of a prior wrong-choice probe."""

    if request.question_type != "CHOICE_WITH_EXPLANATION" or request.answer_spec is None:
        return None
    selected_option_id = typed_choice_selection(request)
    if selected_option_id is None:
        return None
    accepted_choices = {
        normalized_choice_response(answer)
        for answer in [
            request.answer_spec.canonical_answer,
            *request.answer_spec.accepted_answers,
        ]
    }
    if normalized_choice_response(selected_option_id) not in accepted_choices:
        return None
    if "ANSWER_SELECTION" not in objective.confirmed_concept_ids:
        return None
    if "ANSWER_EXPLANATION" not in objective.missing_concept_ids:
        return None
    if selected_general_rule_expression(request) is None:
        return None
    return GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=rules.guided_learning.critical_thinking.choice_reasoning_prompt,
        tutor_message_voice=rules.guided_learning.critical_thinking.choice_reasoning_prompt,
    )


def choice_reasoning_stuck_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Reduce a choice explanation to a concrete comparison after confusion."""

    if request.question_type != "CHOICE_WITH_EXPLANATION":
        return None
    if "ANSWER_SELECTION" not in objective.confirmed_concept_ids:
        return None
    if "ANSWER_EXPLANATION" not in objective.missing_concept_ids:
        return None
    if selected_general_rule_expression(request) is None:
        return None
    normalized = normalize_semantic_answer(request.student_input)
    if normalized not in {
        normalize_semantic_answer(phrase)
        for phrase in rules.guided_learning.critical_thinking.confusion_phrases
    }:
        return None
    message = rules.guided_learning.critical_thinking.choice_reasoning_stuck_prompt
    return GuidedEvaluation(
        student_state="STUCK",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def wrong_direct_rule_evaluation(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Catch a learner rule that contradicts the authored algebra rule."""

    if direct_rule_mismatch(request, rules) is None:
        return None
    message = rules.guided_learning.critical_thinking.wrong_direct_rule_prompt
    return GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=["ANSWER_SELECTION"],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def typed_option_text_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Ask for a click after the learner types exact correct option text."""

    if (
        typed_choice_selection(request) is not None
        or typed_option_text_evidence(request) is None
    ):
        return None
    message = rules.guided_learning.critical_thinking.typed_option_prompt
    return GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def choice_selection_required_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Keep a choice question on selection until the learner chooses an option."""

    if request.question_type != "CHOICE_WITH_EXPLANATION":
        return None
    if "ANSWER_SELECTION" not in objective.missing_concept_ids:
        return None
    if typed_choice_selection(request) is not None:
        return None
    if typed_option_text_evidence(request) is not None:
        return None
    message = rules.guided_learning.critical_thinking.choice_selection_prompt
    return GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def direct_rule_mismatch(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> tuple[tuple[str, str, str], tuple[str, str, str]] | None:
    """Return a direct algebra-rule mismatch without exposing its correction."""

    if request.answer_spec is None:
        return None
    attempted = spoken_expression_parts(request.student_input, rules)
    if attempted is None:
        return None
    canonical_expression = _expression_parts(request.answer_spec.canonical_answer)
    if request.question_type != "CHOICE_WITH_EXPLANATION":
        if canonical_expression is None or attempted == canonical_expression:
            return None
        variable, operator, _ = attempted
        if (
            canonical_expression[0] == variable
            and canonical_expression[1] == operator
        ):
            return attempted, canonical_expression
        return None
    candidate_expressions = [
        expression
        for answer in [request.question, *request.answer_spec.accepted_answers]
        if (expression := _expression_parts(answer)) is not None
    ]
    if attempted in candidate_expressions:
        return None
    variable, operator, _ = attempted
    expected = next(
        (
            expression
            for expression in candidate_expressions
            if expression[0] == variable and expression[1] == operator
        ),
        None,
    )
    return (attempted, expected) if expected is not None else None


def spoken_expression_parts(
    student_input: str,
    rules: ClassifierRulesConfig,
) -> tuple[str, str, str] | None:
    """Parse a compact or spoken learner expression without treating prose as proof."""

    normalized = student_input
    for spoken_number, value in rules.answer_patterns.spoken_number_values.items():
        normalized = re.sub(
            rf"\b{re.escape(spoken_number)}\b",
            format_number_for_matching(value),
            normalized,
            flags=re.IGNORECASE,
        )
    return _expression_parts(normalize_compact_spoken_expression(normalized))


def guided_tutor_context_for(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> GuidedTutorContext:
    """Build the durable teaching context that is authoritative over chat prose."""

    teaching_steps = teaching_steps_for(request)
    active_step = active_teaching_step(request)
    active_question = (
        active_step.prompt
        if active_step is not None
        else focused_unresolved_prompt(
            rubric,
            objective,
            "Which part should we look at first?",
        )
    )
    phase_context = request.phase_2_prompt_context
    support_state = phase_context.support_state if phase_context is not None else {}
    current_support = (
        phase_context.current_support if phase_context is not None else None
    )
    persisted_state = request.guided_teaching_state
    selected_option_id = (
        typed_choice_selection(request)
        or (
            persisted_state.selected_option_id
            if persisted_state is not None
            and persisted_state.question_id == request.question_id
            else None
        )
    )
    selected_option_text = (
        persisted_state.selected_option_text
        if persisted_state is not None
        and persisted_state.question_id == request.question_id
        else None
    )
    current_scaffold_step_number = (
        phase_context.current_scaffold_step_number
        if phase_context is not None
        else 0
    )
    consecutive_stuck_count = (
        phase_context.consecutive_stuck_count if phase_context is not None else 0
    )
    conversation_state_summary = (
        "Confirmed concepts: "
        f"{', '.join(objective.confirmed_concept_ids) or 'none'}. "
        "Missing concepts: "
        f"{', '.join(objective.missing_concept_ids) or 'none'}. "
        f"Active question: {active_question} "
        "If active support is present, explain that exact support in plain language "
        "before asking one focused question about it. "
        "The backend owns progression and support selection; do not advance "
        "or request a support rung."
    )
    authored_step_ids = answer_step_ids_for(request)
    return GuidedTutorContext(
        active_tutor_question=active_question,
        active_step_id=active_step.step_id if active_step is not None else None,
        ordered_teaching_steps=[
            GuidedTeachingPlanStep(
                step_id=teaching_step.step_id,
                tutor_question=teaching_step.prompt,
                answer_step_id=(
                    authored_step_ids[index]
                    if index < len(authored_step_ids)
                    else None
                ),
            )
            for index, teaching_step in enumerate(teaching_steps)
        ],
        confirmed_concept_ids=objective.confirmed_concept_ids,
        missing_concept_ids=objective.missing_concept_ids,
        support_state=support_state,
        current_support=current_support,
        active_support_content=current_support,
        selected_option_id=selected_option_id,
        selected_option_text=selected_option_text,
        active_canvas_events=request.canvas_events,
        canvas_evidence=GuidedCanvasEvidence(
            snapshot_reference=request.canvas_snapshot_reference,
            ocr_regions=[region.model_dump() for region in request.canvas_regions],
            spatial_tokens=[token.model_dump() for token in request.spatial_tokens],
            strokes=request.canvas_strokes,
            ordered_events=request.canvas_events,
        ),
        prior_tutor_response=(
            request.conversation_history[-1].content
            if request.conversation_history
            and request.conversation_history[-1].role == "assistant"
            else None
        ),
        attempt_count=request.attempt_count,
        learning_phase=request.current_phase,
        active_question_anchors=plan_question_anchors(
            request.question_id,
            request.question,
            request.answer_spec,
            active_step.step_id if active_step is not None else None,
        ),
        current_scaffold_step_number=current_scaffold_step_number,
        consecutive_stuck_count=consecutive_stuck_count,
        conversation_state_summary=conversation_state_summary,
        rescue_context=request.rescue_context,
    )


def _numeric_expressions(text: str) -> list[tuple[str, str, str]]:
    """Extract simple numeric examples without interpreting the answer."""

    return [
        (match.group(1), match.group(2), match.group(3))
        for match in re.finditer(r"\b(\d+)\s*([+\-×x*])\s*(\d+)\b", text)
    ]


def copied_example_correction(
    question: str,
    student_input: str,
    objective: ActiveTeachingObjective,
) -> GuidedEvaluation | None:
    """Repair a copied numeric example before progressing to abstract reasoning."""

    question_examples = _numeric_expressions(question)
    for left, operator, right in _numeric_expressions(student_input):
        matching_source = next(
            (
                source
                for source in question_examples
                if source[0] == left and source[1] == operator and source[2] != right
            ),
            None,
        )
        if matching_source is None:
            continue
        expected = f"{matching_source[0]} {matching_source[1]} {matching_source[2]}"
        provided = f"{left} {operator} {right}"
        message = (
            f"Check the example with {left}: the question shows {expected}, not "
            f"{provided}. What number is added each time?"
        )
        return GuidedEvaluation(
            student_state="WRONG",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=message,
            tutor_message_voice=message,
        )
    return None


def source_correction_follow_up(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> GuidedEvaluation | None:
    """Accept the narrow correction that the controller explicitly requested."""

    state = request.guided_teaching_state
    if state is None or state.last_tutor_question_type != "SOURCE_CORRECTION":
        return None
    question_examples = _numeric_expressions(request.question)
    if not question_examples:
        return None
    fixed_numbers = {example[2] for example in question_examples}
    normalized = re.sub(r"[^0-9]", "", request.student_input)
    if normalized not in fixed_numbers:
        return None
    prompt = focused_unresolved_prompt(
        rubric,
        objective,
        "What general rule represents this situation?",
    )
    message = f"Yes. Now use that corrected pattern. {prompt}"
    return GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def option_comparison_follow_up(
    conversation_history: list[ConversationMessage],
    student_input: str,
    objective: ActiveTeachingObjective,
    teaching_state: GuidedTeachingState | None,
) -> GuidedEvaluation | None:
    """Resolve the yes/no check that follows a wrong multiple-choice selection."""

    last_tutor_message = next(
        (
            message.content.casefold()
            for message in reversed(conversation_history)
            if message.role == "assistant"
        ),
        "",
    )
    awaiting_comparison = (
        teaching_state is not None
        and teaching_state.last_tutor_question_type == "OPTION_COMPARISON"
    )
    if (
        "can one fixed starting number describe every possible case" not in last_tutor_message
        and not awaiting_comparison
    ):
        return None

    normalized_response = re.sub(r"[^a-z]", "", student_input.casefold())
    selected_option = (
        teaching_state.selected_option_id.casefold()
        if teaching_state is not None and teaching_state.selected_option_id is not None
        else None
    )
    selected_reference = re.fullmatch(
        r"(?:ichoose(?:option)?|ichose(?:option)?|option|choose)?([a-z])",
        normalized_response,
    )
    if (
        selected_reference is not None
        and selected_option is not None
        and selected_reference.group(1) == selected_option
    ):
        message = (
            "You have already chosen that option. Now test it: can one fixed "
            "starting number describe every possible case?"
        )
        state: GuidedStudentState = "PARTIAL"
    elif normalized_response in {"yes", "yeah", "yep", "correct", "true"}:
        message = (
            "Not quite. A fixed starting number only describes one case. "
            "Try another starting number: would the option you chose still work?"
        )
        state: GuidedStudentState = "WRONG"
    elif normalized_response in {"no", "nope", "false", "incorrect", "itsfalse", "itisfalse"}:
        message = (
            "Right. One fixed starting number cannot describe every case. "
            "Choose the option that uses a changing value, then explain why it works."
        )
        state = "PARTIAL"
    else:
        return None

    return GuidedEvaluation(
        student_state=state,
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def affect_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Put distress and frustration ahead of mathematical diagnosis."""

    normalized = request.student_input.casefold()
    policy = rules.guided_learning.critical_thinking
    if any(phrase in normalized for phrase in policy.distress_phrases):
        message = policy.distress_message
        return GuidedEvaluation(
            student_state="STUCK",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=message,
            tutor_message_voice=message,
        )
    prior_state = request.guided_teaching_state
    if prior_state is not None and prior_state.affect_state == "DISTRESS":
        prompt = active_teaching_step(request)
        question = prompt.prompt if prompt is not None else "Which small part would you like to try first?"
        message = f"We can take this gently. {question}"
        return GuidedEvaluation(
            student_state="PARTIAL",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=message,
            tutor_message_voice=message,
        )
    if any(phrase in normalized for phrase in policy.frustration_phrases):
        prompt = active_teaching_step(request)
        question = prompt.prompt if prompt is not None else "Which part changes from one example to another?"
        message = f"{policy.frustration_acknowledgement} {question}"
        return GuidedEvaluation(
            student_state="STUCK",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=message,
            tutor_message_voice=message,
        )
    return None


def explicit_confusion_evaluation(
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation:
    context = request.phase_2_prompt_context
    repeated = (
        context is not None
        and context.consecutive_stuck_count + 1
        >= rules.strategy_rules.stuck_scaffold_min_count
    )
    selected_option = (
        request.guided_teaching_state.selected_option_text
        if request.guided_teaching_state is not None
        else None
    )
    if repeated:
        message = rules.guided_learning.critical_thinking.repeated_confusion_scaffold_message
    elif selected_option is not None:
        message = rules.guided_learning.critical_thinking.confusion_choice_teaching_probe.format(
            option_text=selected_option,
        )
    else:
        message = rules.guided_learning.critical_thinking.confusion_teaching_probe
    return GuidedEvaluation(
        student_state="STUCK",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def guided_pedagogical_move(
    state: GuidedStudentState,
    consecutive_stuck_count: int,
    stuck_scaffold_min_count: int,
) -> GuidedPedagogicalMove:
    if state == "CORRECT":
        return "ADVANCE"
    if state == "PARTIAL":
        return "REQUEST_EXPLANATION"
    if state == "WRONG":
        return "CORRECT_MISCONCEPTION"
    if state == "STUCK":
        if consecutive_stuck_count + 1 >= stuck_scaffold_min_count:
            return "DELIVER_SUPPORT"
        return "TEACH_AND_PROBE"
    return "ACKNOWLEDGE_AND_PROBE"


def classify_guided_learning_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    openai_client: OpenAIAIEngineClient,
    intent: IntentType,
) -> TutorResponse:
    if request.answer_spec is None or request.question_id is None:
        raise AdapterError(
            "openai_ai_engine",
            "Guided Learning requires question_id and answer_spec.",
        )
    request = request_with_reliable_canvas_evidence(request, rules)
    context = request.phase_2_prompt_context
    if context is None:
        raise AdapterError(
            "openai_ai_engine",
            "Guided Learning requires Phase 2 prompt context.",
        )
    if (
        request.answer_spec.verification_method
        not in rules.guided_learning.supported_verification_methods
    ):
        raise AdapterError(
            "openai_ai_engine",
            (
                "Unsupported Guided Learning verification method "
                f"{request.answer_spec.verification_method} for "
                f"{request.question_id}."
            ),
        )
    allowed_errors = guided_error_definitions(context.potential_errors)
    rubric = resolve_guided_rubric(
        question_id=request.question_id,
        question_type=request.question_type,
        question=request.question,
        answer_spec=request.answer_spec,
        potential_errors=allowed_errors,
        target_micro_skill_ids=context.target_micro_skill_ids,
        existing_rubric=request.generated_question_rubric,
        rules=rules,
        openai_client=openai_client,
    )
    objective = objective_for_rubric(request.active_teaching_objective, rubric)
    objective = objective_with_persisted_choice_selection(request, rubric, objective)
    objective = objective_with_persisted_component_evidence(request, rubric, objective)
    objective = objective_with_turn_evidence(request, rubric, objective, rules)
    affect = affect_evaluation(request, objective, rules)
    if affect is not None:
        return build_guided_tutor_response(request, rules, safety_check, rubric, affect, objective)
    if intent == "EXPRESSING_CONFUSION":
        confusion = explicit_confusion_evaluation(request, objective, rules)
        if context.consecutive_stuck_count + 1 < rules.strategy_rules.stuck_scaffold_min_count:
            confusion = write_deterministic_guided_follow_up(
                confusion,
                request,
                rubric,
                objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, objective),
                rules,
            )
        return build_guided_tutor_response(
            request, rules, safety_check, rubric, confusion, objective
        )
    if intent == "ASKING_QUESTION":
        question_help = explicit_confusion_evaluation(request, objective, rules)
        question_help = write_deterministic_guided_follow_up(
            question_help,
            request,
            rubric,
            objective,
            openai_client,
            allowed_errors,
            guided_tutor_context_for(request, rubric, objective),
            rules,
        )
        return build_guided_tutor_response(
            request, rules, safety_check, rubric, question_help, objective
        )
    copied_example = copied_example_correction(
        request.question,
        request.student_input,
        objective,
    )
    if copied_example is not None:
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            copied_example,
            objective,
        )
    if ambiguous_symbol_number_input(request.student_input):
        ambiguity = GuidedEvaluation(
            student_state="UNCLEAR",
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=None,
            confidence=1.0,
            next_objective=objective,
            tutor_message=rules.guided_learning.critical_thinking.ambiguity_message,
            tutor_message_voice=rules.guided_learning.critical_thinking.ambiguity_message,
        )
        return build_guided_tutor_response(
            request, rules, safety_check, rubric, ambiguity, objective
        )
    corrected_source_follow_up = source_correction_follow_up(
        request,
        rubric,
        objective,
    )
    if corrected_source_follow_up is not None:
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            corrected_source_follow_up,
            objective,
        )
    completed_evidence = completed_evidence_evaluation(objective)
    if completed_evidence is not None:
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            completed_evidence,
            None,
        )
    wrong_choice = wrong_choice_evaluation(request, rubric, objective, rules)
    if wrong_choice is not None:
        return build_guided_tutor_response(
            request, rules, safety_check, rubric, wrong_choice, objective
        )
    correct_choice = correct_choice_selection_evaluation(request, objective, rules)
    if correct_choice is not None:
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            correct_choice,
            objective,
        )
    choice_reasoning_stuck = choice_reasoning_stuck_evaluation(
        request,
        objective,
        rules,
    )
    if choice_reasoning_stuck is not None:
        next_objective = normalized_guided_objective(choice_reasoning_stuck, objective)
        if next_objective is not None:
            choice_reasoning_stuck = write_deterministic_guided_follow_up(
                choice_reasoning_stuck,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            choice_reasoning_stuck,
            next_objective,
        )
    typed_option = typed_option_text_evaluation(request, objective, rules)
    if typed_option is not None:
        next_objective = normalized_guided_objective(typed_option, objective)
        if next_objective is not None:
            typed_option = write_deterministic_guided_follow_up(
                typed_option,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            typed_option,
            next_objective,
        )
    wrong_direct_rule = wrong_direct_rule_evaluation(
        request,
        rubric,
        objective,
        rules,
    )
    if wrong_direct_rule is not None:
        next_objective = normalized_guided_objective(wrong_direct_rule, objective)
        if next_objective is not None:
            wrong_direct_rule = write_deterministic_guided_follow_up(
                wrong_direct_rule,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            wrong_direct_rule,
            next_objective,
        )
    selection_required = choice_selection_required_evaluation(
        request,
        objective,
        rules,
    )
    if selection_required is not None:
        next_objective = normalized_guided_objective(selection_required, objective)
        if next_objective is not None:
            selection_required = write_deterministic_guided_follow_up(
                selection_required,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            selection_required,
            next_objective,
        )
    choice_follow_up = option_comparison_follow_up(
        request.conversation_history,
        request.student_input,
        objective,
        request.guided_teaching_state,
    )
    if choice_follow_up is not None:
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            choice_follow_up,
            objective,
        )
    choice_explanation = deterministic_choice_explanation_evaluation(
        request,
        rubric,
        objective,
        rules,
    )
    if choice_explanation is not None:
        next_objective = normalized_guided_objective(choice_explanation, objective)
        if next_objective is not None:
            choice_explanation = write_deterministic_guided_follow_up(
                choice_explanation,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            choice_explanation,
            next_objective,
        )
    controller_evaluation = (
        None
        if is_authoritative_guided_completion(request)
        else deterministic_teaching_step_evaluation(
            request,
            rubric,
            objective,
            rules,
        )
    )
    if controller_evaluation is not None:
        next_objective = normalized_guided_objective(controller_evaluation, objective)
        if next_objective is not None:
            controller_evaluation = write_deterministic_guided_follow_up(
                controller_evaluation,
                request,
                rubric,
                next_objective,
                openai_client,
                allowed_errors,
                guided_tutor_context_for(request, rubric, next_objective),
                rules,
            )
        return build_guided_tutor_response(
            request,
            rules,
            safety_check,
            rubric,
            controller_evaluation,
            next_objective,
        )
    evaluation: GuidedEvaluation | None = None
    raw_student_state: GuidedStudentState | None = None
    raw_confidence: float | None = None
    last_error: AdapterError | None = None
    rejected_evaluation: GuidedEvaluation | None = None
    validation_feedback: str | None = None
    model_call_count = 0
    guided_tutor_context = guided_tutor_context_for(request, rubric, objective)
    for attempt in range(rules.guided_learning.guided_turn_maximum_retries + 1):
        try:
            model_call_count += 1
            candidate = openai_client.evaluate_guided_turn(
                question_type=request.question_type,
                question=request.question,
                answer_spec=request.answer_spec,
                deterministic_evaluation=evaluate_answer_contract(request),
                generated_rubric=rubric,
                active_objective=objective,
                guided_tutor_context=guided_tutor_context,
                student_response=request.student_input,
                input_source=request.input_source,
                allowed_error_codes=allowed_errors,
                recent_conversation=request.conversation_history[
                    -rules.guided_learning.maximum_recent_history_turns:
                ],
                validation_feedback=validation_feedback,
                evaluator_prompt_version=rules.guided_learning.evaluator_prompt_version,
                system_prompt=rules.guided_learning.evaluator_system_prompt,
            )
            candidate = merge_authored_component_evidence(
                candidate,
                rubric,
                request.student_input,
            )
            candidate = apply_general_rule_explanation_progress(
                candidate,
                request,
                rubric,
                objective,
            )
            raw_student_state = candidate.student_state
            raw_confidence = candidate.confidence
            evaluation = validate_guided_evaluation(
                candidate,
                rubric,
                objective,
                allowed_errors,
                rules,
            )
            if (
                evaluation.student_state != "CORRECT"
                and guided_message_reveals_undemonstrated_answer(
                    evaluation.tutor_message,
                    evaluation.tutor_message_voice,
                    request,
                    evaluation,
                    rules,
                )
            ):
                validation_feedback = (
                    rules.guided_learning.answer_reveal_retry_feedback
                )
                logger.warning(
                    "guided_answer_reveal_retry",
                    extra={
                        "question_id": request.question_id,
                        "attempt": attempt + 1,
                        "student_state": evaluation.student_state,
                    },
                )
                rejected_evaluation = evaluation
                evaluation = None
                continue
            break
        except AdapterError as error:
            last_error = error
            validation_feedback = error.detail
            logger.warning(
                "guided_evaluation_retry",
                extra={
                    "question_id": request.question_id,
                    "attempt": attempt + 1,
                    "detail": error.detail,
                },
            )
    if evaluation is None:
        if rejected_evaluation is not None:
            logger.warning(
                "guided_answer_reveal_safe_message",
                extra={
                    "question_id": request.question_id,
                    "student_state": rejected_evaluation.student_state,
                },
            )
            unresolved_objective = (
                normalized_guided_objective(rejected_evaluation, objective)
                or objective
            )
            safe_message = focused_unresolved_prompt(
                rubric,
                unresolved_objective,
                rules.guided_learning.reconciliation_message,
            )
            evaluation = rejected_evaluation.model_copy(
                update={
                    "tutor_message": safe_message,
                    "tutor_message_voice": safe_message,
                }
            )
        else:
            raise last_error or AdapterError(
                "openai_ai_engine",
                "Guided turn evaluation failed without a validated response.",
            )
    remaining_model_calls = (
        0
        if rules.guided_learning.single_call_enabled
        else max(0, 2 - model_call_count)
    )
    adjudication_targets = component_adjudication_targets(
        evaluation,
        objective,
        rubric,
        request.student_input,
        request.question,
        request.answer_spec,
    )[:remaining_model_calls]
    adjudicator = getattr(openai_client, "adjudicate_component_evidence", None)
    component_evidence_summaries: list[dict[str, str | float]] = []
    if adjudication_targets and callable(adjudicator):
        state_before_adjudication = evaluation.student_state
        for adjudication_target in adjudication_targets:
            logger.info(
                "guided_component_adjudication_started",
                extra={
                    "question_id": request.question_id,
                    "component_id": adjudication_target.concept_id,
                },
            )
            evidence = adjudicator(
                question_type=request.question_type,
                question=request.question,
                answer_spec=request.answer_spec,
                target_component=adjudication_target,
                active_objective=objective,
                student_response=request.student_input,
                input_source=request.input_source,
                recent_conversation=request.conversation_history[
                    -rules.guided_learning.maximum_recent_history_turns:
                ],
                prompt_version=(
                    rules.guided_learning.component_adjudicator_prompt_version
                ),
                system_prompt=(
                    rules.guided_learning.component_adjudicator_system_prompt
                ),
            )
            model_call_count += 1
            evaluation = apply_focused_component_evidence(
                evaluation,
                evidence,
                rules.guided_learning.component_adjudicator_confidence_threshold,
            )
            component_evidence_summaries.append(
                {
                    "component_id": evidence.component_id,
                    "status": evidence.status,
                    "confidence": evidence.confidence,
                }
            )
            logger.info(
                "guided_component_adjudication_completed",
                extra={
                    "question_id": request.question_id,
                    "component_id": evidence.component_id,
                    "status": evidence.status,
                    "confidence": evidence.confidence,
                },
            )
        evaluation = state_from_component_evidence(evaluation, objective, rubric)
        logger.info(
            "guided_component_adjudication_state_derived",
            extra={
                "question_id": request.question_id,
                "state_before_adjudication": state_before_adjudication,
                "student_state": evaluation.student_state,
                "newly_confirmed_concept_ids": evaluation.newly_confirmed_concept_ids,
            },
        )
        evaluation = validate_guided_evaluation(
            evaluation,
            rubric,
            objective,
            allowed_errors,
            rules,
        )
    evaluation = apply_general_rule_explanation_progress(
        evaluation,
        request,
        rubric,
        objective,
    )
    if (
        evaluation.student_state == "PARTIAL"
        and not evaluation.newly_confirmed_concept_ids
    ):
        evaluation = reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            "PARTIAL did not demonstrate a new current-turn component",
        )
    if is_authoritative_guided_completion(request):
        evaluation = authoritative_guided_completion(evaluation, rules)
    next_objective = normalized_guided_objective(evaluation, objective)
    rewrite_candidate = remove_unsupported_guided_praise(evaluation, request)
    rewrite_required = (
        rewrite_candidate.student_state != "CORRECT"
        and next_objective is not None
        and guided_tutor_message_validation_reason(
            rewrite_candidate,
            request,
            rubric,
            next_objective,
            controller_prompt_for_objective(request, rubric, next_objective),
        )
        is not None
    )
    if not rules.guided_learning.single_call_enabled and model_call_count < 2 and rewrite_required:
        evaluation = rewrite_invalid_guided_message_once(
            evaluation,
            request,
            rubric,
            next_objective,
            openai_client,
            allowed_errors,
            guided_tutor_context,
            rules,
        )
        model_call_count += 1
    else:
        evaluation = rewrite_candidate
    evaluation = align_guided_follow_up(
        evaluation,
        request,
        rubric,
        next_objective,
    )
    logger.info(
        "guided_state_evaluated",
        extra={
            "question_id": request.question_id,
            "generated_rubric_hash": rubric.cache_key,
            "active_objective": (
                next_objective.model_dump()
                if next_objective is not None
                else None
            ),
            "student_state": evaluation.student_state,
            "confidence": evaluation.confidence,
            "raw_student_state": raw_student_state,
            "raw_confidence": raw_confidence,
            "selected_error_code": evaluation.selected_error_code,
            "current_turn_evidence_ids": evaluation.newly_confirmed_concept_ids,
            "contradicted_evidence_ids": evaluation.contradicted_concept_ids,
            "pedagogical_move": guided_pedagogical_move(
                evaluation.student_state,
                request.phase_2_prompt_context.consecutive_stuck_count
                if request.phase_2_prompt_context is not None
                else 0,
                rules.strategy_rules.stuck_scaffold_min_count,
            ),
            "model_call_count": model_call_count,
            "student_input_sha256": hashlib.sha256(
                request.student_input.encode("utf-8")
            ).hexdigest(),
            "component_evidence": component_evidence_summaries,
            "tutor_message_sha256": hashlib.sha256(
                evaluation.tutor_message.encode("utf-8")
            ).hexdigest(),
        },
    )
    return build_guided_tutor_response(
        request,
        rules,
        safety_check,
        rubric,
        evaluation,
        next_objective,
    )


def controller_prompt_for_objective(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> str:
    """Return the one controller-owned question for the remaining objective."""

    rules = load_classifier_rules()
    missing_ids = set(objective.missing_concept_ids)
    if (
        request.question_type == "CHOICE_WITH_EXPLANATION"
        and "ANSWER_SELECTION" not in missing_ids
        and "ANSWER_EXPLANATION" in missing_ids
    ):
        general_rule_evidence = general_rule_explanation_evidence(request)
        if general_rule_evidence == (True, False):
            expression = selected_general_rule_expression(request)
            if expression is not None:
                return rules.guided_learning.general_rule_fixed_value_prompt.format(
                    variable=expression.group(1)
                )
        if general_rule_evidence == (False, True):
            return rules.guided_learning.general_rule_changing_value_prompt
        return (
            "Why does the option you chose work for every case in the question?"
        )
    for teaching_step in teaching_steps_for(request):
        component_id = _component_for_step(request, rubric, teaching_step.step_id)
        if component_id in missing_ids:
            return teaching_step.prompt
    return focused_unresolved_prompt(
        rubric,
        objective,
        "Which part should we look at first?",
    )


def write_deterministic_guided_follow_up(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    openai_client: OpenAIAIEngineClient,
    allowed_errors: list[dict[str, object]],
    guided_tutor_context: GuidedTutorContext,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation:
    """Let OpenAI phrase a backend-selected next teaching target."""

    controller_prompt = (
        evaluation.tutor_message
        if evaluation.tutor_message.rstrip().endswith("?")
        else controller_prompt_for_objective(request, rubric, objective)
    )
    writer = getattr(openai_client, "write_guided_fact_budget_message", None)
    if not callable(writer):
        return evaluation
    wording_context = guided_fact_budget_context(
        evaluation,
        request,
        objective,
        controller_prompt,
        rules,
    )
    try:
        candidate = writer(
            system_prompt=rules.guided_learning.fact_budget_wording_system_prompt,
            wording_context=wording_context,
        )
    except AdapterError as error:
        logger.warning(
            "guided_deterministic_wording_failed",
            extra={
                "question_id": request.question_id,
                "detail": error.detail,
                "active_prompt_sha256": hashlib.sha256(
                    controller_prompt.encode("utf-8")
                ).hexdigest(),
            },
        )
        raise

    rewritten = evaluation.model_copy(
        update={
            "tutor_message": candidate.tutor_message,
            "tutor_message_voice": candidate.tutor_message_voice_optimised,
        }
    )
    rewritten = remove_unsupported_guided_praise(rewritten, request)
    rejection_reason = guided_tutor_message_validation_reason(
        rewritten,
        request,
        rubric,
        objective,
        controller_prompt,
    )
    if rejection_reason is None:
        logger.info(
            "guided_deterministic_wording_openai_accepted",
            extra={
                "question_id": request.question_id,
                "active_prompt_sha256": hashlib.sha256(
                    controller_prompt.encode("utf-8")
                ).hexdigest(),
            },
        )
        return rewritten
    if rules.guided_learning.single_call_enabled:
        logger.warning(
            "guided_deterministic_wording_rejected",
            extra={
                "question_id": request.question_id,
                "rejection_reason": rejection_reason,
                "active_prompt_sha256": hashlib.sha256(
                    controller_prompt.encode("utf-8")
                ).hexdigest(),
            },
        )
        return evaluation
    try:
        retry = writer(
            system_prompt=rules.guided_learning.fact_budget_wording_system_prompt,
            wording_context={
                **wording_context,
                "validation_feedback": (
                    f"The previous wording was rejected for {rejection_reason}. "
                    "Keep the same active question and do not disclose an "
                    "unresolved answer."
                ),
            },
        )
    except AdapterError as error:
        logger.warning(
            "guided_deterministic_wording_rewrite_failed",
            extra={
                "question_id": request.question_id,
                "rejection_reason": rejection_reason,
                "detail": error.detail,
            },
        )
        raise
    retried = evaluation.model_copy(
        update={
            "tutor_message": retry.tutor_message,
            "tutor_message_voice": retry.tutor_message_voice_optimised,
        }
    )
    retry_reason = guided_tutor_message_validation_reason(
        retried,
        request,
        rubric,
        objective,
        controller_prompt,
    )
    if retry_reason is None:
        logger.info(
            "guided_deterministic_wording_rewrite_accepted",
            extra={
                "question_id": request.question_id,
                "initial_rejection_reason": rejection_reason,
                "active_prompt_sha256": hashlib.sha256(
                    controller_prompt.encode("utf-8")
                ).hexdigest(),
            },
        )
        return retried
    logger.warning(
        "guided_deterministic_wording_rejected",
        extra={
            "question_id": request.question_id,
            "rejection_reason": rejection_reason,
            "rewrite_rejection_reason": retry_reason,
            "active_prompt_sha256": hashlib.sha256(
                controller_prompt.encode("utf-8")
            ).hexdigest(),
        },
    )
    raise AdapterError(
        "openai_ai_engine",
        f"Guided wording remained invalid after one retry: {retry_reason}.",
    )


def guided_fact_budget_context(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
    controller_prompt: str,
    rules: ClassifierRulesConfig,
) -> dict[str, object]:
    """Build the writer context without passing the hidden canonical answer."""

    confirmed_ids = set(objective.confirmed_concept_ids)
    confirmed_ids.update(evaluation.newly_confirmed_concept_ids)
    confirmed_ids.update(evaluation.preserved_concept_ids)
    confirmed_ids.difference_update(evaluation.contradicted_concept_ids)
    allowed_facts = ["The learner's latest words: " + request.student_input]
    phase_context = request.phase_2_prompt_context
    consecutive_stuck_count = (
        phase_context.consecutive_stuck_count if phase_context is not None else 0
    )
    pedagogical_move = guided_pedagogical_move(
        evaluation.student_state,
        consecutive_stuck_count,
        rules.strategy_rules.stuck_scaffold_min_count,
    )
    authorised_teaching_facts: list[str] = []
    if pedagogical_move == "TEACH_AND_PROBE" and phase_context is not None:
        hints = phase_context.support_catalog.get("hints")
        if isinstance(hints, list):
            first_hint = next(
                (
                    hint.get("content")
                    for hint in hints
                    if isinstance(hint, dict) and isinstance(hint.get("content"), str)
                ),
                None,
            )
            if first_hint is not None:
                authorised_teaching_facts.append(first_hint)
    expression = _expression_parts(
        request.answer_spec.canonical_answer if request.answer_spec else ""
    )
    if expression is not None:
        variable, operator, fixed_value = expression
        if "CHANGING_VALUE" in confirmed_ids:
            allowed_facts.append(f"{variable} is a changing quantity.")
        if "FIXED_VALUE" in confirmed_ids:
            allowed_facts.append(f"{fixed_value} is fixed.")
        if "OPERATION" in confirmed_ids:
            allowed_facts.append(
                f"The learner identified the operation as {operation_word(operator)}."
            )
        active_step = active_teaching_step(request)
        if active_step is not None and evaluation.newly_confirmed_concept_ids:
            active_fact = {
                "CHANGING_VALUE": f"The learner identified {variable} as changing.",
                "FIXED_VALUE": f"The learner identified {fixed_value} as fixed.",
                "OPERATION": (
                    "The learner identified the operation as "
                    f"{operation_word(operator)}."
                ),
            }.get(active_step.step_id)
            if active_fact is not None:
                allowed_facts.append(active_fact)
    direct_rule_error = direct_rule_mismatch(request, rules)
    typed_option = typed_option_text_evidence(request)
    role_contradiction = active_role_contradiction(request)
    return {
        "question": request.question,
        "student_response": request.student_input,
        "input_source": request.input_source,
        "student_state": evaluation.student_state,
        "active_tutor_question": controller_prompt,
        "pedagogical_move": pedagogical_move,
        "authorised_teaching_facts": authorised_teaching_facts,
        "recent_tutor_questions": [
            message.content
            for message in request.conversation_history[-4:]
            if message.role == "assistant"
        ],
        "confirmed_concept_ids": sorted(confirmed_ids),
        "missing_concept_ids": objective.missing_concept_ids,
        "last_turn_evidence": (
            [
                claim.model_dump()
                for claim in request.guided_teaching_state.last_turn_evidence
                if claim.status == "DEMONSTRATED"
            ]
            if request.guided_teaching_state is not None
            else []
        ),
        "forbidden_question_concept_ids": sorted(
            confirmed_ids - set(evaluation.newly_confirmed_concept_ids)
        ),
        "allowed_facts": allowed_facts,
        "abstract_rule_shape": "[changing quantity] [operation] [fixed value]",
        "diagnostic": (
            {
                "focus": "FIXED_AMOUNT_PREMISE_ERROR",
                "evidence": (
                    "The fixed amount in the learner's typed expression conflicts "
                    "with the repeated amount in the authored examples or options."
                ),
                "required_move": (
                    "Use the visible examples or support to ask the learner to "
                    "compare the repeated amount. Do not state the corrected "
                    "amount or complete rule."
                ),
            }
            if direct_rule_error is not None
            else {
                "focus": role_contradiction,
                "evidence": (
                    "The learner assigned an expression part a role that "
                    "contradicts the active teaching target."
                ),
                "required_move": (
                    "Ask one Socratic contrast question about the active role. "
                    "Do not move to another role or reveal the answer."
                ),
            }
            if role_contradiction is not None
            else {
                "focus": "TYPED_OPTION_NOT_SELECTED",
                "evidence": (
                    "The learner typed the text of an authored option but has "
                    "not selected its option control."
                ),
                "required_move": (
                    "Acknowledge the matched rule without confirming completion, "
                    "then ask the learner to select the matching option."
                ),
            }
            if typed_option is not None
            else None
        ),
        "support_context": (
            support_context_text(request.phase_2_prompt_context.current_support)
            if request.phase_2_prompt_context is not None
            and request.phase_2_prompt_context.current_support is not None
            else None
        ),
        "recent_conversation": [
            message.model_dump()
            for message in request.conversation_history[
                -rules.guided_learning.maximum_recent_history_turns:
            ]
        ],
    }


def operation_word(operator: str) -> str:
    """Return a learner-facing operation name for confirmed evidence only."""

    return {
        "+": "addition",
        "-": "subtraction",
        "×": "multiplication",
        "x": "multiplication",
        "*": "multiplication",
    }.get(operator, "the operation")


def rewrite_invalid_guided_message_once(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective | None,
    openai_client: OpenAIAIEngineClient,
    allowed_errors: list[dict[str, object]],
    guided_tutor_context: GuidedTutorContext,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation:
    """Ask the LLM once to repair invalid prose without changing teaching state."""

    if evaluation.student_state == "CORRECT" or objective is None:
        return evaluation

    evaluation = remove_unsupported_guided_praise(evaluation, request)
    controller_prompt = controller_prompt_for_objective(request, rubric, objective)
    rejection_reason = guided_tutor_message_validation_reason(
        evaluation,
        request,
        rubric,
        objective,
        controller_prompt,
    )
    if rejection_reason is None:
        return evaluation

    logger.warning(
        "guided_tutor_message_rewrite_requested",
        extra={
            "question_id": request.question_id,
            "student_state": evaluation.student_state,
            "rejection_reason": rejection_reason,
            "active_prompt_sha256": hashlib.sha256(
                controller_prompt.encode("utf-8")
            ).hexdigest(),
        },
    )
    try:
        rewritten = openai_client.evaluate_guided_turn(
            question_type=request.question_type,
            question=request.question,
            answer_spec=request.answer_spec,
            deterministic_evaluation=evaluate_answer_contract(request),
            generated_rubric=rubric,
            active_objective=objective,
            guided_tutor_context=guided_tutor_context,
            student_response=request.student_input,
            input_source=request.input_source,
            allowed_error_codes=allowed_errors,
            recent_conversation=request.conversation_history[
                -rules.guided_learning.maximum_recent_history_turns:
            ],
            validation_feedback=guided_message_rewrite_feedback(
                rejection_reason,
                controller_prompt,
            ),
            evaluator_prompt_version=rules.guided_learning.evaluator_prompt_version,
            system_prompt=rules.guided_learning.evaluator_system_prompt,
        )
    except AdapterError as error:
        logger.warning(
            "guided_tutor_message_rewrite_failed",
            extra={
                "question_id": request.question_id,
                "student_state": evaluation.student_state,
                "rejection_reason": rejection_reason,
                "detail": error.detail,
            },
        )
        raise

    rewritten_evaluation = evaluation.model_copy(
        update={
            "tutor_message": rewritten.tutor_message,
            "tutor_message_voice": rewritten.tutor_message_voice,
        }
    )
    rewritten_evaluation = remove_unsupported_guided_praise(
        rewritten_evaluation,
        request,
    )
    rewritten_reason = guided_tutor_message_validation_reason(
        rewritten_evaluation,
        request,
        rubric,
        objective,
        controller_prompt,
    )
    if rewritten_reason is None:
        logger.info(
            "guided_tutor_message_rewrite_accepted",
            extra={
                "question_id": request.question_id,
                "student_state": evaluation.student_state,
                "initial_rejection_reason": rejection_reason,
            },
        )
        return rewritten_evaluation

    logger.warning(
        "guided_tutor_message_rewrite_rejected",
        extra={
            "question_id": request.question_id,
            "student_state": evaluation.student_state,
            "initial_rejection_reason": rejection_reason,
            "rewritten_rejection_reason": rewritten_reason,
        },
    )
    raise AdapterError(
        "openai_ai_engine",
        f"Guided message remained invalid after one rewrite: {rewritten_reason}.",
    )


def guided_message_rewrite_feedback(
    rejection_reason: str,
    controller_prompt: str,
) -> str:
    """Tell the LLM how to repair only its wording for one guided turn."""

    variation_instruction = (
        "Do not repeat or closely paraphrase a recent tutor question. Choose a "
        "smaller concrete probe for the same objective. "
        if rejection_reason == "NEAR_DUPLICATE"
        else ""
    )
    return (
        "Your previous tutor wording was rejected for "
        f"{rejection_reason}. Keep the same student-state classification and "
        "component evidence. Rewrite only tutor_message and tutor_message_voice. "
        f"{variation_instruction}"
        "Respond naturally to the student's exact words or misconception, do not "
        "reveal any unresolved answer, and end with one focused question about "
        f"the active step: {controller_prompt}"
    )


def align_guided_follow_up(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective | None,
) -> GuidedEvaluation:
    """Replace empty, unsafe, generic, or off-topic LLM wording with the active question."""

    if evaluation.student_state == "CORRECT" or objective is None:
        return evaluation
    evaluation = remove_unsupported_guided_praise(
        evaluation,
        request,
    )
    prompt = controller_prompt_for_objective(request, rubric, objective)
    rejection_reason = guided_tutor_message_validation_reason(
        evaluation,
        request,
        rubric,
        objective,
        prompt,
    )
    if rejection_reason is None:
        return evaluation
    if rejection_reason == "NEAR_DUPLICATE":
        raise AdapterError(
            "openai_ai_engine",
            "Guided tutor wording repeated a recent tutor question after rewrite.",
        )
    prefix = {
        "PARTIAL": "Good.",
        "WRONG": "Let's check that carefully.",
        "STUCK": "That's okay.",
        "UNCLEAR": "Let's focus on this part.",
    }[evaluation.student_state]
    acknowledgement = safe_guided_acknowledgement_prefix(
        evaluation,
        request,
        rubric,
        objective,
    )
    message = f"{acknowledgement or prefix} {prompt}"
    logger.warning(
        "guided_tutor_message_replaced",
        extra={
            "question_id": request.question_id,
            "student_state": evaluation.student_state,
            "active_prompt": prompt,
            "rejection_reason": rejection_reason,
        },
    )
    return evaluation.model_copy(
        update={
            "tutor_message": message,
            "tutor_message_voice": message,
        }
    )


def remove_unsupported_guided_praise(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
) -> GuidedEvaluation:
    """Remove only praise that is not supported by this turn's component evidence."""

    confirmed_component_ids = {
        *evaluation.newly_confirmed_concept_ids,
        *evaluation.preserved_concept_ids,
    } - set(evaluation.contradicted_concept_ids)
    tutor_message = remove_unsupported_praise_sentences(
        evaluation.tutor_message,
        request,
        confirmed_component_ids,
    )
    tutor_message_voice = remove_unsupported_praise_sentences(
        evaluation.tutor_message_voice,
        request,
        confirmed_component_ids,
    )
    if (
        tutor_message == evaluation.tutor_message
        and tutor_message_voice == evaluation.tutor_message_voice
    ):
        return evaluation
    logger.warning(
        "guided_unsupported_praise_removed",
        extra={
            "question_id": request.question_id,
            "student_state": evaluation.student_state,
            "confirmed_component_ids": sorted(confirmed_component_ids),
        },
    )
    return evaluation.model_copy(
        update={
            "tutor_message": tutor_message,
            "tutor_message_voice": tutor_message_voice,
        }
    )


def remove_unsupported_praise_sentences(
    message: str,
    request: ClassificationRequest,
    confirmed_component_ids: set[str],
) -> str:
    """Keep useful correction prose while removing only unsupported praise clauses."""

    sentences = re.split(r"(?<=[.!?])\s+", message.strip())
    retained_sentences = []
    for sentence in sentences:
        if not unsupported_guided_praise_sentence(
            sentence,
            request,
            confirmed_component_ids,
        ):
            retained_sentences.append(sentence)
            continue
        correction = correction_after_unsupported_praise(sentence)
        if correction is not None:
            retained_sentences.append(correction)
    return " ".join(retained_sentences)


def unsupported_guided_praise_sentence(
    sentence: str,
    request: ClassificationRequest,
    confirmed_component_ids: set[str],
) -> bool:
    """Return whether praise claims evidence that the evaluation does not support."""

    normalized = normalize_semantic_answer(sentence)
    praise_terms = (
        "correct",
        "good",
        "great",
        "nice",
        "right",
        "youve got it",
        "got it",
        "well done",
        "on the right track",
    )
    if not any(term in normalized for term in praise_terms):
        return False
    if "youve got it" in normalized or "got it" in normalized:
        return True
    if not confirmed_component_ids:
        return True

    expression = _expression_parts(
        request.answer_spec.canonical_answer if request.answer_spec else ""
    )
    if expression is None:
        return False
    variable, _, fixed_value = expression
    if re.search(
        rf"\b{re.escape(variable)}\b\s+(?:is|stays|remains)\s+(?:fixed|constant)",
        normalized,
    ):
        return True
    if re.search(
        rf"\b{re.escape(fixed_value)}\b\s+(?:is|can|does)\s+(?:change|vary|changes|varies)",
        normalized,
    ):
        return True

    return False


def correction_after_unsupported_praise(sentence: str) -> str | None:
    """Keep the corrective clause when it follows unsupported praise with 'but'."""

    match = re.search(r"\bbut\s+(.+)", sentence, flags=re.IGNORECASE)
    if match is None:
        return None
    correction = match.group(1).strip()
    return correction if correction else None


def guided_tutor_message_is_safe_and_relevant(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    controller_prompt: str,
) -> bool:
    """Return whether the LLM reply is safe and tied to the current tutor turn."""

    return (
        guided_tutor_message_validation_reason(
            evaluation,
            request,
            rubric,
            objective,
            controller_prompt,
        )
        is None
    )


def guided_tutor_message_validation_reason(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    controller_prompt: str,
) -> str | None:
    """Return the precise reason a guided message cannot be shown unchanged."""

    message = evaluation.tutor_message.strip()
    voice_message = evaluation.tutor_message_voice.strip()
    if message == "" or voice_message == "":
        return "EMPTY"

    rules = load_classifier_rules()
    similarity = maximum_recent_tutor_message_similarity(message, request)
    if similarity >= rules.guided_learning.tutor_message_similarity_threshold:
        logger.warning(
            "guided_duplicate_tutor_question_rejected",
            extra={
                "question_id": request.question_id,
                "student_state": evaluation.student_state,
                "similarity": round(similarity, 3),
            },
        )
        return "NEAR_DUPLICATE"
    if guided_message_reveals_undemonstrated_answer(
        message,
        voice_message,
        request,
        evaluation,
        rules,
    ):
        return "ANSWER_REVEAL"

    if guided_message_reveals_active_unresolved_teaching_step(
        message,
        request,
        rubric,
        objective,
    ):
        return "ACTIVE_STEP_REVEAL"

    if guided_message_reveals_multiple_unresolved_teaching_steps(
        message,
        request,
        rubric,
        objective,
    ):
        return "ANSWER_REVEAL"

    if guided_message_mislabels_current_role(
        message,
        request,
        rubric,
        evaluation,
    ):
        return "MISALIGNED_ACKNOWLEDGEMENT"
    if guided_message_acknowledges_non_turn_evidence(message, request, rubric, rules):
        return "STALE_ACKNOWLEDGEMENT"

    if guided_message_asserts_wrong_fixed_amount(message, request):
        return "UNSUPPORTED_FIXED_AMOUNT"

    if guided_message_reveals_fixed_amount_for_mismatched_rule(message, request):
        return "FIXED_AMOUNT_REVEAL"

    if evaluation.student_state == "STUCK" and not guided_message_keeps_controller_focus(
        message,
        controller_prompt,
    ):
        return "ACTIVE_PROMPT_DRIFT"

    explanation_probe_reason = general_rule_explanation_probe_reason(
        message,
        request,
        objective,
    )
    if explanation_probe_reason is not None:
        return explanation_probe_reason

    normalized_message = normalize_semantic_answer(message)

    if (
        evaluation.selected_error_code is not None
        and guided_message_repairs_selected_misconception(normalized_message)
    ):
        return None

    message_tokens = significant_component_tokens(message)
    if (
        objective.objective_type == "EXPLAIN_REASONING"
        and message_tokens.intersection(
            {"explain", "reason", "reasoning", "support", "supports", "why"}
        )
    ):
        return None
    turn_context_tokens = (
        significant_component_tokens(request.student_input)
        | significant_component_tokens(request.question)
    )
    if message_tokens.intersection(turn_context_tokens):
        return None
    if message_tokens.intersection(significant_component_tokens(controller_prompt)):
        return None
    if message_tokens.intersection(active_support_context_tokens(request)):
        return None
    if guided_message_mentions_selected_option(normalized_message, request):
        return None
    return "UNRELATED"


def maximum_recent_tutor_message_similarity(
    message: str,
    request: ClassificationRequest,
) -> float:
    candidate_tokens = significant_component_tokens(message)
    similarities: list[float] = []
    for prior in request.conversation_history[-4:]:
        if prior.role != "assistant":
            continue
        prior_tokens = significant_component_tokens(prior.content)
        union = candidate_tokens | prior_tokens
        if not union:
            similarities.append(
                1.0
                if normalize_semantic_answer(message)
                == normalize_semantic_answer(prior.content)
                else 0.0
            )
            continue
        similarities.append(len(candidate_tokens & prior_tokens) / len(union))
    return max(similarities, default=0.0)


def guided_message_asserts_wrong_fixed_amount(
    message: str,
    request: ClassificationRequest,
) -> bool:
    """Reject a writer claim that repeats the learner's incorrect fixed amount."""
    expected = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    attempted = _expression_parts(request.student_input)
    if expected is None or attempted is None:
        return False
    if attempted[0] != expected[0] or attempted[1] != expected[1]:
        return False
    attempted_fixed = attempted[2]
    if attempted_fixed == expected[2]:
        return False

    normalized = normalize_semantic_answer(message)
    assertion_patterns = (
        rf"\ball\s+(?:the\s+)?examples?\b.*\b{re.escape(attempted_fixed)}\b",
        rf"\beach\s+(?:example|case)\b.*\b{re.escape(attempted_fixed)}\b",
        rf"\bevery\s+(?:example|case)\b.*\b{re.escape(attempted_fixed)}\b",
        rf"\b{re.escape(attempted_fixed)}\b.*\b(?:stays|fixed|constant|consistent)\b",
    )
    return any(re.search(pattern, normalized) is not None for pattern in assertion_patterns)


def guided_message_reveals_fixed_amount_for_mismatched_rule(
    message: str,
    request: ClassificationRequest,
) -> bool:
    """Keep a correction prompt from naming the amount the learner must inspect."""

    expected = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    attempted = _expression_parts(request.student_input)
    if expected is None or attempted is None:
        return False
    if attempted[0] != expected[0] or attempted[1] != expected[1]:
        return False
    if attempted[2] == expected[2]:
        return False
    expected_fixed_value = expected[2]
    return (
        re.search(
            rf"\b{re.escape(expected_fixed_value)}\b",
            normalize_semantic_answer(message),
        )
        is not None
    )


def guided_message_keeps_controller_focus(
    message: str,
    controller_prompt: str,
) -> bool:
    """Require a stuck-turn rewrite to preserve the controller's reduced task."""

    controller_tokens = significant_component_tokens(controller_prompt)
    if not controller_tokens:
        return True
    return len(significant_component_tokens(message).intersection(controller_tokens)) >= 2


def guided_message_mislabels_current_role(
    message: str,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    evaluation: GuidedEvaluation,
) -> bool:
    """Reject praise that names an earlier role instead of this turn's evidence."""

    active_step = active_teaching_step(request)
    if active_step is None:
        return False
    component_id = _component_for_step(request, rubric, active_step.step_id)
    if component_id not in evaluation.newly_confirmed_concept_ids:
        return False
    first_sentence = re.split(r"[.!?]", message.casefold(), maxsplit=1)[0]
    acknowledgement = r"(?:right|correct|identified|noted|said|found)"
    if active_step.step_id == "FIXED_VALUE":
        return re.search(rf"\b{acknowledgement}\b.*\bchang", first_sentence) is not None
    if active_step.step_id == "CHANGING_VALUE":
        return re.search(rf"\b{acknowledgement}\b.*\b(?:fixed|constant|same)", first_sentence) is not None
    return False


def guided_message_acknowledges_non_turn_evidence(
    message: str,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    rules: ClassifierRulesConfig,
) -> bool:
    """Reject praise that claims the learner showed a role on an earlier turn."""

    first_sentence = re.split(r"[.!?]", message.casefold(), maxsplit=1)[0]
    if re.search(r"\b(?:right|correct|identified|noted|said|found|great)\b", first_sentence) is None:
        return False
    current_ids = {
        claim.concept_id
        for claim in deterministic_turn_evidence(request, rubric, rules)
        if claim.status == "DEMONSTRATED"
    }
    role_words = {
        "CHANGING_VALUE": r"\b(?:changing|changes|variable)\b",
        "FIXED_VALUE": r"\b(?:fixed|constant|stays|same|remains)\b",
        "OPERATION": r"\b(?:operation|addition|subtraction|plus|minus)\b",
    }
    for step_id, pattern in role_words.items():
        component_id = _component_for_step(request, rubric, step_id)
        if (
            component_id is not None
            and component_id not in current_ids
            and re.search(pattern, first_sentence) is not None
        ):
            return True
    return False


def general_rule_explanation_probe_reason(
    message: str,
    request: ClassificationRequest,
    objective: ActiveTeachingObjective,
) -> str | None:
    """Keep a general-rule explanation on the one fact the learner still needs."""

    if (
        request.question_type != "CHOICE_WITH_EXPLANATION"
        or "ANSWER_SELECTION" not in objective.confirmed_concept_ids
        or "ANSWER_EXPLANATION" not in objective.missing_concept_ids
    ):
        return None
    evidence = general_rule_explanation_evidence(request)
    if evidence is None:
        return None
    normalized_message = normalize_semantic_answer(message)
    changing_identified, fixed_identified = evidence
    if changing_identified and not fixed_identified:
        if not re.search(r"\b(?:fixed|constant|same|stay|stays|remains)\b", normalized_message):
            return "WRONG_EXPLANATION_PROBE"
    if fixed_identified and not changing_identified:
        if not re.search(r"\b(?:change|changes|changing|variable|vary|varies)\b", normalized_message):
            return "WRONG_EXPLANATION_PROBE"
    return None


def active_support_context_tokens(request: ClassificationRequest) -> set[str]:
    """Return meaningful words from the currently displayed authored support."""

    phase_context = request.phase_2_prompt_context
    if phase_context is None or phase_context.current_support is None:
        return set()
    return significant_component_tokens(
        support_context_text(phase_context.current_support)
    )


def support_context_text(value: object) -> str:
    """Flatten the small support payload into text for relevance validation."""

    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(support_context_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(support_context_text(item) for item in value)
    return ""


def guided_message_mentions_selected_option(
    normalized_message: str,
    request: ClassificationRequest,
) -> bool:
    """Keep a response that directly addresses the student's persisted choice."""

    state = request.guided_teaching_state
    if state is None or state.question_id != request.question_id:
        return False
    option_id = state.selected_option_id
    option_text = state.selected_option_text
    if option_id is not None and re.search(
        rf"\boption\s+{re.escape(option_id.casefold())}\b",
        normalized_message,
    ):
        return True
    if option_text is None:
        return False
    option_tokens = significant_component_tokens(option_text)
    return bool(option_tokens and option_tokens.intersection(
        significant_component_tokens(normalized_message)
    ))


def guided_message_reveals_multiple_unresolved_teaching_steps(
    message: str,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> bool:
    """Reject prose that supplies several pending steps in one tutor turn.

    A focused correction may name one idea to repair a misconception.  It must
    not, however, complete the rest of a multi-part response for the learner.
    """

    answer_spec = request.answer_spec
    if answer_spec is None:
        return False
    expression = _expression_parts(answer_spec.canonical_answer) or _expression_parts(
        request.question
    )
    active_step = active_teaching_step(request)
    if expression is None or active_step is None:
        return False

    variable, operator, fixed_value = expression
    teaching_steps = teaching_steps_for(request)
    active_index = next(
        (
            index
            for index, teaching_step in enumerate(teaching_steps)
            if teaching_step.step_id == active_step.step_id
        ),
        None,
    )
    if active_index is None:
        return False
    missing_step_ids = {
        teaching_step.step_id
        for teaching_step in teaching_steps[active_index:]
        if _component_for_step(request, rubric, teaching_step.step_id)
        in set(objective.missing_concept_ids)
    }
    if not missing_step_ids:
        return False

    if (
        "GENERAL_RULE" in objective.missing_concept_ids
        and message_contains_canonical_answer(message, message, request)
        and not learner_input_matches_canonical_answer(request)
    ):
        return True

    normalized = normalize_semantic_answer(message)
    normalized_student_input = normalize_semantic_answer(request.student_input)
    revealed_step_count = 0
    if (
        "CHANGING_VALUE" in missing_step_ids
        and not teaches_changing_value(
            normalized_student_input,
            variable,
        )
        and teaches_changing_value(
            normalized,
            variable,
        )
    ):
        revealed_step_count += 1
    if (
        "FIXED_VALUE" in missing_step_ids
        and not teaches_fixed_value(
            normalized_student_input,
            fixed_value,
        )
        and teaches_fixed_value(
            normalized,
            fixed_value,
        )
    ):
        revealed_step_count += 1
    operation_terms = operation_answer_terms(operator)
    if (
        "OPERATION" in missing_step_ids
        and not teaches_operation(normalized_student_input, operation_terms)
        and teaches_operation(normalized, operation_terms)
    ):
        revealed_step_count += 1
    return revealed_step_count >= 2


def guided_message_reveals_active_unresolved_teaching_step(
    message: str,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> bool:
    """Reject a reply that supplies the unanswered role the tutor just asked for."""

    answer_spec = request.answer_spec
    active_step = active_teaching_step(request)
    if answer_spec is None or active_step is None:
        return False
    expression = _expression_parts(answer_spec.canonical_answer) or _expression_parts(
        request.question
    )
    if expression is None:
        return False
    component_id = _component_for_step(request, rubric, active_step.step_id)
    if component_id is None or component_id not in objective.missing_concept_ids:
        return False
    variable, operator, fixed_value = expression
    learner_words = normalize_semantic_answer(request.student_input)
    tutor_words = normalize_semantic_answer(message)
    if active_step.step_id == "CHANGING_VALUE":
        return (
            not teaches_changing_value(learner_words, variable)
            and teaches_changing_value(tutor_words, variable)
        )
    if active_step.step_id == "FIXED_VALUE":
        return (
            not teaches_fixed_value(learner_words, fixed_value)
            and teaches_fixed_value(tutor_words, fixed_value)
        )
    if active_step.step_id == "OPERATION":
        operation_terms = operation_answer_terms(operator)
        return (
            not teaches_operation(learner_words, operation_terms)
            and teaches_operation(tutor_words, operation_terms)
        )
    return False


def teaches_changing_value(message: str, variable: str) -> bool:
    """Return whether prose directly supplies the changing-value answer."""

    escaped_variable = re.escape(variable)
    return bool(
        re.search(
            rf"\b(?:changing (?:quantity|value)|variable|letter|symbol)\b"
            rf"[^.?!]{{0,32}}\b{escaped_variable}\b",
            message,
        )
        or re.search(
            rf"\b{escaped_variable}\b\s+(?:(?:is|represents)\s+(?:a\s+)?"
            r"(?:changing\s+(?:quantity|value)|variable)|can\s+change|varies)",
            message,
        )
    )


def teaches_fixed_value(message: str, fixed_value: str) -> bool:
    """Return whether prose directly supplies the fixed-value answer."""

    escaped_value = re.escape(fixed_value)
    return bool(
        re.search(
            rf"\b(?:fixed value|fixed number|constant|increment)\b"
            rf"[^.?!]{{0,32}}\b{escaped_value}\b",
            message,
        )
        or re.search(
            rf"\b{escaped_value}\b\s+(?:is|stays|remains)\s+(?:fixed|constant)",
            message,
        )
    )


def teaches_operation(message: str, operation_terms: set[str]) -> bool:
    """Return whether prose directly supplies the pending operation answer."""

    alternatives = "|".join(sorted(map(re.escape, operation_terms)))
    return bool(
        re.search(
            rf"\b(?:operation|plus sign|minus sign|sign)\b"
            rf"[^.?!]{{0,32}}\b(?:{alternatives})\b",
            message,
        )
    )


def operation_answer_terms(operator: str) -> set[str]:
    """Return verbal answer terms that disclose an operation step."""

    terms_by_operator = {
        "+": {"add", "added", "adding", "addition", "plus"},
        "-": {"subtract", "subtracted", "subtracting", "subtraction", "minus"},
        "×": {"multiply", "multiplied", "multiplying", "multiplication", "times"},
        "x": {"multiply", "multiplied", "multiplying", "multiplication", "times"},
        "*": {"multiply", "multiplied", "multiplying", "multiplication", "times"},
    }
    return terms_by_operator[operator]


def safe_guided_acknowledgement_prefix(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> str | None:
    """Keep a safe brief acknowledgement while replacing an unsafe explanation."""

    first_sentence = re.split(r"(?<=[.!?])\s+", evaluation.tutor_message.strip())[0]
    acknowledgement_starts = (
        "good",
        "great",
        "nice",
        "yes",
        "you are right",
        "you're right",
        "youre right",
        "you are on the right track",
        "you're on the right track",
        "youre on the right track",
    )
    if not first_sentence.casefold().startswith(acknowledgement_starts):
        return None
    if guided_message_reveals_unresolved_teaching_step(
        first_sentence,
        request,
        rubric,
        objective,
    ):
        return None
    return first_sentence


def guided_message_repairs_selected_misconception(normalized_message: str) -> bool:
    """Recognise specific corrective wording when surface tokens differ."""

    correction_terms = {
        "add",
        "added",
        "adding",
        "addition",
        "decrease",
        "decreased",
        "decreasing",
        "divide",
        "divided",
        "dividing",
        "division",
        "increase",
        "increased",
        "increasing",
        "minus",
        "multiply",
        "multiplied",
        "multiplying",
        "multiplication",
        "plus",
        "subtract",
        "subtracted",
        "subtracting",
        "subtraction",
        "variable",
        "fixed",
        "constant",
    }
    return (
        len(significant_component_tokens(normalized_message)) >= 3
        and bool(set(normalized_message.split()).intersection(correction_terms))
    )


def guided_message_reveals_undemonstrated_answer(
    message: str,
    voice_message: str,
    request: ClassificationRequest,
    evaluation: GuidedEvaluation,
    rules: ClassifierRulesConfig,
) -> bool:
    """Block a final answer only when the learner has not already supplied it."""

    if not message_reveals_answer(
        message,
        voice_message,
        request.correct_answer,
        rules,
    ) and not message_contains_canonical_answer(message, voice_message, request):
        return False
    return not guided_turn_has_answer_evidence(request, evaluation)


def message_contains_canonical_answer(
    message: str,
    voice_message: str,
    request: ClassificationRequest,
) -> bool:
    """Detect a canonical answer in tutor prose even without correct_answer."""

    if request.answer_spec is None:
        return False
    canonical = normalize_semantic_answer(request.answer_spec.canonical_answer)
    if canonical == "":
        return False
    for candidate in (message, voice_message):
        normalized = normalize_semantic_answer(candidate)
        if len(canonical) == 1 and canonical.isalnum():
            if re.search(rf"(?<!\w){re.escape(canonical)}(?!\w)", normalized):
                return True
        elif canonical in normalized:
            return True
    return False


def guided_turn_has_answer_evidence(
    request: ClassificationRequest,
    evaluation: GuidedEvaluation,
) -> bool:
    """Return whether this turn or its durable state already proves the answer."""

    if learner_input_matches_canonical_answer(request):
        return True
    return guided_choice_selection_is_confirmed(request, evaluation)


def learner_input_matches_canonical_answer(request: ClassificationRequest) -> bool:
    """Recognise a full canonical answer already present in the learner input."""

    if request.answer_spec is None:
        return False
    if request.question_type in {
        "CHOICE_WITH_EXPLANATION",
        "TRUE_FALSE_WITH_EXPLANATION",
    } or request.answer_spec.verification_method == "EXACT_CHOICE_MATCH":
        return normalized_choice_response(request.student_input) in {
            normalized_choice_response(answer)
            for answer in [
                request.answer_spec.canonical_answer,
                *request.answer_spec.accepted_answers,
            ]
        }
    canonical_answer = normalize_semantic_answer(
        request.answer_spec.canonical_answer
    )
    learner_answer = normalize_semantic_answer(request.student_input)
    if canonical_answer == "" or learner_answer == "":
        return False
    if len(canonical_answer) == 1 and canonical_answer.isalnum():
        return re.search(
            rf"(?<!\w){re.escape(canonical_answer)}(?!\w)",
            learner_answer,
        ) is not None
    return canonical_answer in learner_answer


def guided_choice_selection_is_confirmed(
    request: ClassificationRequest,
    evaluation: GuidedEvaluation,
) -> bool:
    """Allow explanation of the correct choice once the learner selected it."""

    if request.answer_spec is None:
        return False
    if request.question_type not in {
        "CHOICE_WITH_EXPLANATION",
        "TRUE_FALSE_WITH_EXPLANATION",
    }:
        return False
    teaching_state = request.guided_teaching_state
    if teaching_state is None or teaching_state.selected_option_id is None:
        return False
    accepted_choices = {
        normalized_choice_response(answer)
        for answer in [
            request.answer_spec.canonical_answer,
            *request.answer_spec.accepted_answers,
        ]
    }
    selected_choice = normalized_choice_response(teaching_state.selected_option_id)
    if selected_choice not in accepted_choices:
        return False
    learner_choice = normalized_choice_response(request.student_input)
    if len(learner_choice) == 1 and learner_choice.isalpha() and learner_choice != selected_choice:
        return False
    confirmed_ids = {
        *evaluation.newly_confirmed_concept_ids,
        *evaluation.preserved_concept_ids,
    }
    return "ANSWER_SELECTION" in confirmed_ids


def authoritative_guided_completion(
    evaluation: GuidedEvaluation,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation:
    """Keep a proven answer correct without inventing component evidence."""
    return evaluation.model_copy(
        update={
            "student_state": "CORRECT",
            "newly_confirmed_concept_ids": [],
            "preserved_concept_ids": [],
            "contradicted_concept_ids": [],
            "missing_concept_ids": [],
            "selected_error_code": None,
            "next_objective": None,
            "tutor_message": rules.messages.CORRECT,
            "tutor_message_voice": rules.messages.CORRECT,
        }
    )


def explicitly_demonstrates_all_teaching_steps(request: ClassificationRequest) -> bool:
    """Allow a complete multi-part answer to finish in one learner turn."""

    expression = (
        _expression_parts(request.answer_spec.canonical_answer)
        if request.answer_spec is not None
        else None
    ) or _expression_parts(request.question)
    if expression is None:
        return False
    variable, operator, fixed_value = expression
    normalized = request.student_input.casefold()
    compact = re.sub(r"\s+", "", normalized)
    operation_words = (
        ("add", "addition", "plus")
        if operator == "+"
        else ("subtract", "subtraction", "minus")
    )
    evidence_by_step = {
        "GENERAL_RULE": re.fullmatch(
            rf".*{re.escape(variable)}\s*{re.escape(operator)}\s*{fixed_value}.*",
            compact,
        )
        is not None,
        "CHANGING_VALUE": variable in normalized
        and any(word in normalized for word in ("change", "changing", "varies", "variable", "any", "different")),
        "FIXED_VALUE": fixed_value in normalized
        and any(word in normalized for word in ("fixed", "constant", "stays", "same", "remains")),
        "OPERATION": any(word in normalized for word in operation_words),
    }
    return all(
        evidence_by_step.get(step.step_id, False)
        for step in teaching_steps_for(request)
        if step.step_id != "DEFENCE"
    )


def is_authoritative_guided_completion(
    request: ClassificationRequest,
) -> bool:
    """Return whether the contract has proven the whole requested response."""
    if evaluate_answer_contract(request) != "CORRECT" or request.answer_spec is None:
        return False
    # A correct expression is only one part of a Guided Practice response when
    # the authored question also asks the learner to identify its roles.
    # Let the controller complete those ordered steps before allowing the
    # answer contract to close the question.
    if teaching_steps_for(request) and not explicitly_demonstrates_all_teaching_steps(request):
        return False
    if (
        request.answer_spec.explanation_required
        and request.answer_spec.verification_method == "EXACT_CHOICE_MATCH"
    ):
        return False
    rules = load_classifier_rules()
    if (
        request.question_type == "MULTI_PART_SHORT_RESPONSE"
        or requires_multi_component_completion(request, rules)
    ):
        return normalize_semantic_answer(request.student_input) == normalize_semantic_answer(
            request.answer_spec.canonical_answer
        )
    return True


def guided_error_definitions(
    potential_errors: list[dict[str, object]],
) -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = []
    for potential_error in potential_errors:
        error_code = potential_error.get("error_code")
        description = (
            potential_error.get("description")
            or potential_error.get("error_description")
        )
        response_patterns = potential_error.get("response_patterns")
        if not isinstance(error_code, str):
            continue
        definitions.append(
            {
                "error_code": error_code,
                "description": description if isinstance(description, str) else "",
                "response_patterns": (
                    [
                        pattern
                        for pattern in response_patterns
                        if isinstance(pattern, str)
                    ]
                    if isinstance(response_patterns, list)
                    else []
                ),
            }
        )
    return definitions


def validate_generated_rubric(
    rubric: GeneratedQuestionRubric,
    question_id: str,
    question_type: QuestionType | None,
    answer_spec: AnswerSpec,
    rules: ClassifierRulesConfig,
) -> None:
    concept_ids = [concept.concept_id for concept in rubric.required_concepts]
    if rubric.question_id != question_id:
        raise AdapterError(
            "openai_ai_engine",
            f"Rubric question_id {rubric.question_id} does not match {question_id}.",
        )
    if not concept_ids or len(concept_ids) != len(set(concept_ids)):
        raise AdapterError(
            "openai_ai_engine",
            f"Rubric for {question_id} has empty or duplicate concept IDs.",
        )
    if (
        requires_multi_component_rubric(question_type, answer_spec, rules)
        and len(
            [
                concept
                for concept in rubric.required_concepts
                if concept.required
            ]
        )
        < 2
    ):
        raise AdapterError(
            "openai_ai_engine",
            (
                f"Rubric for {question_id} must contain separate required "
                "concepts for every answer component."
            ),
        )


_COMPONENT_TOKEN_ALIASES = {
    "added": "add",
    "addition": "add",
    "adding": "add",
    "adds": "add",
    "changed": "change",
    "changes": "change",
    "changing": "change",
    "constant": "fixed",
    "remains": "stay",
    "stays": "stay",
    "unchanged": "fixed",
}
_COMPONENT_LINKING_TOKENS = {
    "a",
    "an",
    "is",
    "means",
    "operation",
    "quantity",
    "the",
    "value",
    "stay",
}
_NEGATION_PATTERN = re.compile(r"\b(?:not|isn't|isnt|doesn't|doesnt|never)\b")
_GENERAL_RULE_EXPRESSION_RE = re.compile(
    r"\b([a-z])\s*([+\-−])\s*(\d+)\b",
    re.IGNORECASE,
)


def component_evidence_tokens(value: str) -> set[str]:
    """Normalize harmless wording differences in one authored answer part."""

    normalized_tokens = {
        _COMPONENT_TOKEN_ALIASES.get(token, token)
        for token in normalize_semantic_answer(value).split()
    }
    return normalized_tokens - _COMPONENT_LINKING_TOKENS


def authored_component_is_demonstrated(
    component: GeneratedConcept,
    response_tokens: set[str],
    normalized_response: str,
) -> bool:
    if not component.concept_id.startswith("REQUIRED_COMPONENT_"):
        return False
    required_tokens = component_evidence_tokens(component.description)
    return bool(required_tokens) and required_tokens.issubset(response_tokens)


def concise_explanation_is_demonstrated(
    component: GeneratedConcept,
    response_tokens: set[str],
) -> bool:
    """Recognise a short valid reason without demanding a fixed sentence form."""

    component_kind = f"{component.concept_id} {component.description}".casefold()
    is_reason_component = any(
        term in component_kind
        for term in ("explanation", "explain", "reason", "why")
    )
    if not is_reason_component:
        return False
    justification_tokens = {"variable", "change", "different", "any", "represent"}
    return bool(response_tokens.intersection(justification_tokens))


def general_rule_explanation_evidence(
    request: ClassificationRequest,
) -> tuple[bool, bool] | None:
    """Return the two ideas needed to justify a variable-plus-constant choice."""

    if request.question_type != "CHOICE_WITH_EXPLANATION":
        return None
    # By the time this runs ANSWER_SELECTION is confirmed, so the selected
    # option's own text is the correct source. Searching the raw question
    # instead can match a distractor's expression when one is authored
    # first, locking the evidence check onto the wrong variable/constant.
    expression = selected_general_rule_expression(request)
    if expression is None:
        return None
    variable, _operator, fixed_value = expression.groups()
    learner_text = " ".join(
        [
            *(message.content for message in request.conversation_history if message.role == "user"),
            request.student_input,
        ]
    ).casefold()
    variable_pattern = re.compile(
        rf"\b{re.escape(variable)}\b.*\b(?:change|changes|changing|variable|any|different)\b"
        rf"|\b(?:change|changes|changing|variable|any|different)\b.*\b{re.escape(variable)}\b"
    )
    active_probe = (
        request.guided_teaching_state.last_reasoning_probe.casefold()
        if request.guided_teaching_state is not None
        and request.guided_teaching_state.last_reasoning_probe is not None
        else ""
    )
    concise_variable_answer = (
        re.search(r"\b(?:any|changing|different|variable)\b", request.student_input.casefold())
        is not None
        and re.search(rf"\b{re.escape(variable)}\b", active_probe) is not None
    )
    fixed_pattern = re.compile(
        rf"(?<!\d)[+\-−]?\s*{re.escape(fixed_value)}(?!\d).*"
        r"\b(?:fixed|constant|stay|stays|same)\b"
        rf"|\b(?:fixed|constant|stay|stays|same)\b.*(?<!\d)[+\-−]?\s*{re.escape(fixed_value)}(?!\d)"
    )
    concise_fixed_answer = re.fullmatch(
        rf"[+\-−]?\s*{re.escape(fixed_value)}", request.student_input.casefold().strip()
    ) is not None and any(
        phrase in active_probe
        for phrase in ("stays fixed", "stays the same", "value stays fixed", "fixed value")
    )
    demonstrated_reasoning_ids = (
        set(request.guided_teaching_state.demonstrated_reasoning_ids)
        if request.guided_teaching_state is not None
        else set()
    )
    return (
        variable_pattern.search(learner_text) is not None
        or concise_variable_answer
        or "GENERAL_RULE_CHANGING_VALUE" in demonstrated_reasoning_ids,
        fixed_pattern.search(learner_text) is not None
        or concise_fixed_answer
        or "GENERAL_RULE_FIXED_VALUE" in demonstrated_reasoning_ids,
    )


def selected_general_rule_expression(
    request: ClassificationRequest,
) -> re.Match[str] | None:
    """Find the rule being explained, preferring the learner's selected option."""

    selected_option_text = (
        request.guided_teaching_state.selected_option_text
        if request.guided_teaching_state is not None
        else None
    )
    return _GENERAL_RULE_EXPRESSION_RE.search(
        (selected_option_text or request.question).casefold()
    )


def deterministic_choice_explanation_evaluation(
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation | None:
    """Keep a selected general-rule choice on its changing-then-fixed path."""

    if request.question_type != "CHOICE_WITH_EXPLANATION":
        return None
    if "ANSWER_SELECTION" not in objective.confirmed_concept_ids:
        return None
    if "ANSWER_EXPLANATION" not in objective.missing_concept_ids:
        return None
    evidence = general_rule_explanation_evidence(request)
    if evidence is None:
        return None
    changing_identified, fixed_identified = evidence
    if not changing_identified and not fixed_identified:
        return None
    if changing_identified and fixed_identified:
        return GuidedEvaluation(
            student_state="CORRECT",
            newly_confirmed_concept_ids=["ANSWER_EXPLANATION"],
            preserved_concept_ids=objective.confirmed_concept_ids,
            contradicted_concept_ids=[],
            missing_concept_ids=[],
            selected_error_code=None,
            confidence=1.0,
            next_objective=None,
            tutor_message=rules.messages.CORRECT,
            tutor_message_voice=rules.messages.CORRECT,
        )
    expression = selected_general_rule_expression(request)
    if changing_identified and expression is not None:
        message = rules.guided_learning.general_rule_fixed_value_prompt.format(
            variable=expression.group(1)
        )
    elif fixed_identified:
        message = rules.guided_learning.general_rule_changing_value_prompt
    else:
        return None
    return GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=objective.confirmed_concept_ids,
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=1.0,
        next_objective=objective,
        tutor_message=message,
        tutor_message_voice=message,
    )


def apply_general_rule_explanation_progress(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
) -> GuidedEvaluation:
    """Keep a general-rule explanation on the changing-then-fixed teaching path."""

    evidence = general_rule_explanation_evidence(request)
    if evidence is None:
        return evaluation
    changing_identified, fixed_identified = evidence
    explanation_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if component.required and "explanation" in component.concept_id.casefold()
    }
    selection_confirmed = "ANSWER_SELECTION" in {
        *objective.confirmed_concept_ids,
        *evaluation.newly_confirmed_concept_ids,
        *evaluation.preserved_concept_ids,
    }
    if not explanation_ids or not selection_confirmed:
        return evaluation

    newly_confirmed_ids = set(evaluation.newly_confirmed_concept_ids)
    missing_ids = set(evaluation.missing_concept_ids)
    if changing_identified and fixed_identified:
        newly_confirmed_ids.update(explanation_ids)
        missing_ids.difference_update(explanation_ids)
        return evaluation.model_copy(
            update={
                "student_state": "CORRECT",
                "newly_confirmed_concept_ids": sorted(newly_confirmed_ids),
                "missing_concept_ids": sorted(missing_ids),
            }
        )

    # Naming only one part is useful evidence, but not the full explanation.
    # Do not let a broad LLM interpretation skip the remaining fixed/changing cue.
    newly_confirmed_ids.difference_update(explanation_ids)
    missing_ids.update(explanation_ids)
    return evaluation.model_copy(
        update={
            "student_state": "PARTIAL",
            "newly_confirmed_concept_ids": sorted(newly_confirmed_ids),
            "missing_concept_ids": sorted(missing_ids),
        }
    )


def contradicted_authored_component_ids(
    rubric: GeneratedQuestionRubric,
    student_input: str,
) -> set[str]:
    """Detect a direct reversal such as saying a fixed addend changes."""

    response_tokens = component_evidence_tokens(normalize_semantic_answer(student_input))
    property_tokens = {"change", "fixed"}
    operation_tokens = {"add", "subtract", "multiply", "divide"}
    response_property = next(
        (token for token in property_tokens if token in response_tokens),
        None,
    )
    if response_property is None:
        return set()
    normalized_input = student_input.casefold()
    contradicted: set[str] = set()
    for component in rubric.required_concepts:
        component_tokens = component_evidence_tokens(component.description)
        component_property = next(
            (token for token in property_tokens if token in component_tokens),
            None,
        )
        component_terms = component_tokens - property_tokens - operation_tokens
        describes_reversed_component = any(
            re.search(
                (
                    rf"(?<![a-z0-9]){re.escape(term)}(?:\s+is)?\s+"
                    rf"{response_property}(?:s|d|ing)?\b"
                ),
                normalized_input,
            )
            is not None
            for term in component_terms
        )
        if (
            component_property is not None
            and component_property != response_property
            and describes_reversed_component
        ):
            contradicted.add(component.concept_id)
    return contradicted


def merge_authored_component_evidence(
    evaluation: GuidedEvaluation,
    rubric: GeneratedQuestionRubric,
    student_input: str,
) -> GuidedEvaluation:
    """Confirm clear lexical paraphrases without replacing semantic LLM review."""

    if _NEGATION_PATTERN.search(student_input.lower()) is not None:
        return evaluation
    normalized_response = normalize_semantic_answer(student_input)
    response_tokens = component_evidence_tokens(normalized_response)
    directly_contradicted_ids = contradicted_authored_component_ids(
        rubric,
        student_input,
    )
    if directly_contradicted_ids:
        required_ids = {
            component.concept_id
            for component in rubric.required_concepts
            if component.required
        }
        return evaluation.model_copy(
            update={
                "student_state": "WRONG",
                "newly_confirmed_concept_ids": [],
                "contradicted_concept_ids": sorted(
                    set(evaluation.contradicted_concept_ids)
                    | directly_contradicted_ids
                ),
                "missing_concept_ids": sorted(required_ids),
            }
        )
    demonstrated_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if (
            authored_component_is_demonstrated(
                component,
                response_tokens,
                normalized_response,
            )
            or concise_explanation_is_demonstrated(component, response_tokens)
        )
    }
    if not demonstrated_ids:
        return evaluation
    contradicted_ids = set(evaluation.contradicted_concept_ids)
    newly_confirmed_ids = (
        set(evaluation.newly_confirmed_concept_ids) | demonstrated_ids
    ) - contradicted_ids
    confirmed_ids = (
        newly_confirmed_ids | set(evaluation.preserved_concept_ids)
    ) - contradicted_ids
    required_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if component.required
    }
    missing_ids = required_ids - confirmed_ids - contradicted_ids
    # A small lexical reason can prevent a repeat loop, but it cannot by itself
    # promote an answer to complete; only deterministic completion or validated
    # semantic evaluation may do that.
    student_state: GuidedStudentState = (
        "CORRECT" if evaluation.student_state == "CORRECT" else "PARTIAL"
    )
    return evaluation.model_copy(
        update={
            "student_state": student_state,
            "newly_confirmed_concept_ids": sorted(newly_confirmed_ids),
            "missing_concept_ids": sorted(missing_ids),
        }
    )


def significant_component_tokens(value: str) -> set[str]:
    """Return cheap relevance tokens while retaining numbers and variables."""

    tokens = set(normalize_semantic_answer(value).split())
    ignored = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "because",
        "briefly",
        "can",
        "does",
        "explain",
        "for",
        "how",
        "is",
        "it",
        "of",
        "or",
        "the",
        "this",
        "to",
        "what",
        "which",
        "why",
        "with",
    }
    return {
        token
        for token in tokens - ignored
        if len(token) >= 3 or token.isdigit() or token.isalpha() and len(token) == 1
    }


def component_adjudication_targets(
    evaluation: GuidedEvaluation,
    objective: ActiveTeachingObjective,
    rubric: GeneratedQuestionRubric,
    student_response: str,
    question: str,
    answer_spec: AnswerSpec,
) -> list[GeneratedConcept]:
    """Verify claimed evidence before it can enter persistent guided state."""

    claimed_ids = set(evaluation.newly_confirmed_concept_ids) - set(
        objective.confirmed_concept_ids
    )
    claimed = [
        component
        for component in rubric.required_concepts
        if component.required and component.concept_id in claimed_ids
    ]
    if claimed:
        return claimed

    if (
        evaluation.student_state != "PARTIAL"
        or evaluation.contradicted_concept_ids
        or not objective.confirmed_concept_ids
        or not evaluation.missing_concept_ids
        or not student_response.strip()
    ):
        return []
    missing_ids = set(evaluation.missing_concept_ids)
    target = next(
        (
            component
            for component in rubric.required_concepts
            if component.required and component.concept_id in missing_ids
        ),
        None,
    )
    if target is None:
        return []
    response_tokens = significant_component_tokens(student_response)
    context = " ".join(
        [
            target.description,
            question,
            answer_spec.canonical_answer,
            *answer_spec.accepted_answers,
        ]
    )
    if not response_tokens.intersection(significant_component_tokens(context)):
        return []
    return [target]


def apply_focused_component_evidence(
    evaluation: GuidedEvaluation,
    evidence: FocusedComponentEvidence,
    confidence_threshold: float,
) -> GuidedEvaluation:
    """Apply independently verified evidence to one authored component."""

    confirmed_ids = set(evaluation.newly_confirmed_concept_ids)
    contradicted_ids = set(evaluation.contradicted_concept_ids)
    if (
        evidence.status == "DEMONSTRATED"
        and evidence.confidence >= confidence_threshold
    ):
        confirmed_ids.add(evidence.component_id)
        contradicted_ids.discard(evidence.component_id)
    else:
        # A model claim is never persistent evidence on its own. If the
        # independent adjudicator cannot positively demonstrate the component,
        # remove the new claim and retain the unresolved teaching step.
        confirmed_ids.discard(evidence.component_id)
        if (
            evidence.status == "CONTRADICTED"
            and evidence.confidence >= confidence_threshold
        ):
            contradicted_ids.add(evidence.component_id)
    return evaluation.model_copy(
        update={
            "newly_confirmed_concept_ids": sorted(confirmed_ids),
            "contradicted_concept_ids": sorted(contradicted_ids),
        }
    )


def state_from_component_evidence(
    evaluation: GuidedEvaluation,
    objective: ActiveTeachingObjective,
    rubric: GeneratedQuestionRubric,
) -> GuidedEvaluation:
    """Derive completion from validated component evidence, never an adjudicator state."""

    required_ids = {
        component.concept_id
        for component in rubric.required_concepts
        if component.required
    }
    confirmed_ids = (
        set(objective.confirmed_concept_ids)
        | set(evaluation.newly_confirmed_concept_ids)
    ) - set(evaluation.contradicted_concept_ids)
    remaining_ids = required_ids - confirmed_ids
    if not remaining_ids:
        return evaluation.model_copy(update={"student_state": "CORRECT"})
    if set(evaluation.newly_confirmed_concept_ids) - set(
        objective.confirmed_concept_ids
    ):
        return evaluation.model_copy(update={"student_state": "PARTIAL"})
    if evaluation.student_state == "CORRECT":
        return evaluation.model_copy(update={"student_state": "UNCLEAR"})
    return evaluation


def initial_guided_objective(
    rubric: GeneratedQuestionRubric,
) -> ActiveTeachingObjective:
    required_ids = [
        concept.concept_id
        for concept in rubric.required_concepts
        if concept.required
    ]
    return ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=required_ids,
        confirmed_concept_ids=[],
        missing_concept_ids=required_ids,
    )


def validate_guided_evaluation(
    evaluation: GuidedEvaluation,
    rubric: GeneratedQuestionRubric,
    objective: ActiveTeachingObjective,
    allowed_errors: list[dict[str, object]],
    rules: ClassifierRulesConfig,
) -> GuidedEvaluation:
    concept_ids = {concept.concept_id for concept in rubric.required_concepts}
    returned_ids = {
        *evaluation.newly_confirmed_concept_ids,
        *evaluation.contradicted_concept_ids,
    }
    if not returned_ids.issubset(concept_ids):
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            f"unknown concept IDs: {sorted(returned_ids - concept_ids)}",
        )
    allowed_error_codes = {
        item["error_code"]
        for item in allowed_errors
        if isinstance(item.get("error_code"), str)
    }
    if (
        evaluation.selected_error_code is not None
        and evaluation.selected_error_code not in allowed_error_codes
    ):
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            f"disallowed error code: {evaluation.selected_error_code}",
        )
    if evaluation.student_state not in rules.guided_learning.allowed_student_states:
        raise AdapterError(
            "openai_ai_engine",
            f"Guided evaluation returned disallowed state {evaluation.student_state}.",
        )
    state_threshold = rules.guided_learning.state_confidence_thresholds.get(
        evaluation.student_state
    )
    if state_threshold is None:
        raise AdapterError(
            "openai_ai_engine",
            (
                "No confidence threshold is configured for Guided Learning "
                f"state {evaluation.student_state}."
            ),
        )
    if evaluation.confidence < state_threshold:
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            (
                f"confidence {evaluation.confidence} below "
                f"{evaluation.student_state} threshold {state_threshold}"
            ),
        )
    contradicted = set(evaluation.contradicted_concept_ids)
    confirmed = (
        set(objective.confirmed_concept_ids)
        | set(evaluation.newly_confirmed_concept_ids)
    ) - contradicted
    required_ids = {
        concept.concept_id
        for concept in rubric.required_concepts
        if concept.required
    }
    expected_missing = required_ids - confirmed
    remaining = set(expected_missing)
    if (
        not evaluation.tutor_message.strip()
        or not evaluation.tutor_message_voice.strip()
    ):
        raise AdapterError(
            "openai_ai_engine",
            "Guided evaluation must return non-empty text and voice messages.",
        )
    if not remaining:
        return evaluation.model_copy(
            update={
                "student_state": "CORRECT",
                "preserved_concept_ids": sorted(
                    set(objective.confirmed_concept_ids) - contradicted
                ),
                "missing_concept_ids": [],
                "selected_error_code": None,
                "next_objective": None,
                "tutor_message": rules.messages.CORRECT,
                "tutor_message_voice": rules.messages.CORRECT,
            }
        )
    if evaluation.student_state == "CORRECT" and remaining:
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            "CORRECT left required concepts missing",
        )
    if (
        evaluation.student_state == "PARTIAL"
        and not confirmed
        and remaining
        and evaluation.selected_error_code is not None
    ):
        # PARTIAL requires positive evidence for at least one authored
        # component. When the model found only an authored misconception, this
        # is an incorrect attempt, not an unclear partial. Preserving that error
        # lets the deterministic Wrong-1..Wrong-4 ladder reach its scaffold.
        evaluation = evaluation.model_copy(update={"student_state": "WRONG"})
    if evaluation.student_state == "PARTIAL" and (not confirmed or not remaining):
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            "PARTIAL did not contain both confirmed and missing concepts",
        )
    if evaluation.student_state in {"STUCK", "UNCLEAR"} and (
        evaluation.newly_confirmed_concept_ids
        or evaluation.selected_error_code is not None
    ):
        return reconcile_guided_evaluation(
            evaluation,
            objective,
            rubric,
            rules,
            f"{evaluation.student_state} attempted to create evidence",
        )
    next_objective = (
        None
        if evaluation.student_state == "CORRECT"
        else ActiveTeachingObjective(
            objective_type=(
                evaluation.next_objective.objective_type
                if evaluation.next_objective is not None
                else objective.objective_type
            ),
            target_concept_ids=sorted(remaining),
            confirmed_concept_ids=sorted(confirmed),
            missing_concept_ids=sorted(remaining),
        )
    )
    return evaluation.model_copy(
        update={
            "preserved_concept_ids": sorted(
                set(objective.confirmed_concept_ids) - contradicted
            ),
            "missing_concept_ids": sorted(remaining),
            "next_objective": next_objective,
        }
    )


def reconcile_guided_evaluation(
    evaluation: GuidedEvaluation,
    objective: ActiveTeachingObjective,
    rubric: GeneratedQuestionRubric,
    rules: ClassifierRulesConfig,
    reason: str,
) -> GuidedEvaluation:
    logger.warning(
        "guided_state_reconciled",
        extra={
            "raw_student_state": evaluation.student_state,
            "raw_confidence": evaluation.confidence,
            "reason": reason,
        },
    )
    message = focused_unresolved_prompt(
        rubric,
        objective,
        rules.guided_learning.reconciliation_message,
    )
    return evaluation.model_copy(
        update={
            "student_state": "UNCLEAR",
            "newly_confirmed_concept_ids": [],
            "preserved_concept_ids": objective.confirmed_concept_ids,
            "contradicted_concept_ids": [],
            "missing_concept_ids": objective.missing_concept_ids,
            "selected_error_code": None,
            "next_objective": objective,
            "tutor_message": message,
            "tutor_message_voice": message,
        }
    )


def requires_multi_component_rubric(
    question_type: QuestionType | None,
    answer_spec: AnswerSpec,
    rules: ClassifierRulesConfig,
) -> bool:
    return (
        question_type in rules.guided_learning.multi_component_question_types
        or answer_spec.explanation_required is True
    )


def requires_multi_component_completion(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    if request.answer_spec is None:
        return False
    return requires_multi_component_rubric(
        request.question_type,
        request.answer_spec,
        rules,
    )


def normalized_guided_objective(
    evaluation: GuidedEvaluation,
    previous: ActiveTeachingObjective,
) -> ActiveTeachingObjective | None:
    if evaluation.student_state == "CORRECT":
        return None
    contradicted = set(evaluation.contradicted_concept_ids)
    confirmed = (
        set(previous.confirmed_concept_ids)
        | set(evaluation.preserved_concept_ids)
        | set(evaluation.newly_confirmed_concept_ids)
    ) - contradicted
    missing = set(evaluation.missing_concept_ids) | contradicted
    target_ids = (
        evaluation.next_objective.target_concept_ids
        if evaluation.next_objective is not None
        else sorted(missing)
    )
    return ActiveTeachingObjective(
        objective_type=(
            evaluation.next_objective.objective_type
            if evaluation.next_objective is not None
            else "EXPLAIN_CONCEPT"
        ),
        target_concept_ids=target_ids,
        confirmed_concept_ids=sorted(confirmed),
        missing_concept_ids=sorted(missing),
    )


def build_guided_tutor_response(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    safety_check: SafetyCheck,
    rubric: GeneratedQuestionRubric,
    evaluation: GuidedEvaluation,
    objective: ActiveTeachingObjective | None,
) -> TutorResponse:
    state = evaluation.student_state
    phase_context = request.phase_2_prompt_context
    consecutive_stuck_count = (
        phase_context.consecutive_stuck_count if phase_context is not None else 0
    )
    pedagogical_move = guided_pedagogical_move(
        state,
        consecutive_stuck_count,
        rules.strategy_rules.stuck_scaffold_min_count,
    )
    diagnostic_focus = (
        "SOURCE_CORRECTION"
        if prompt_type_for_message(evaluation.tutor_message) == "SOURCE_CORRECTION"
        else "INPUT_AMBIGUITY"
        if state == "UNCLEAR"
        else "AFFECT"
        if "you are not stupid" in evaluation.tutor_message.casefold()
        else "UNSUPPORTED_GENERALISATION"
        if prompt_type_for_message(evaluation.tutor_message) == "DEFENCE"
        else "ACTIVE_OBJECTIVE"
    )
    pedagogy_archetype = (
        "SOCRATIC_COUNTEREXAMPLE"
        if state == "WRONG"
        else "PROGRESSIVE_LOAD_REDUCTION"
        if state == "STUCK"
        else "HYPATIA_DEFENCE"
        if prompt_type_for_message(evaluation.tutor_message) == "DEFENCE"
        else "AFFIRM_THEN_ISOLATE"
    )
    logger.info(
        "guided_turn_diagnostics",
        extra={
            "question_id": request.question_id,
            "message_source": "controller" if evaluation.confidence == 1.0 else "openai",
            "openai_model": openai_model_for_request(get_settings(), request),
            "diagnostic_focus": diagnostic_focus,
            "pedagogy_archetype": pedagogy_archetype,
            "detected_intent": detect_student_intent(request.student_input, rules),
            "pedagogical_move": pedagogical_move,
            "consecutive_stuck_count": consecutive_stuck_count,
            "confirmed_concept_ids": objective.confirmed_concept_ids if objective is not None else [],
            "missing_concept_ids": objective.missing_concept_ids if objective is not None else [],
            "turn_evidence": [
                claim.model_dump()
                for claim in deterministic_turn_evidence(request, rubric, rules)
            ],
            "completion_decision": "ADVANCE" if objective is None else "CONTINUE",
        },
    )
    review_request = request.model_copy(
        update={
            "generated_question_rubric": rubric,
            "active_teaching_objective": objective,
        }
    )
    canvas_review: CanvasMathReview | None = _canvas_review_for(
        review_request,
        rules,
        evaluation.confidence,
    )
    response_strategy: ResponseStrategy = (
        "CONFIRM_CORRECT"
        if state == "CORRECT"
        else "CLARIFY"
        if state in {"PARTIAL", "STUCK", "UNCLEAR"}
        else "ENCOURAGE_RETRY"
    )
    mapped_evaluation: EvaluationCategory = (
        "CORRECT"
        if state == "CORRECT"
        else "PARTIALLY_CORRECT"
        if state == "PARTIAL"
        else "INCORRECT"
        if state == "WRONG"
        else "NO_ATTEMPT"
        if state == "STUCK"
        else "UNCLEAR"
    )
    response = TutorResponse(
        evaluation=mapped_evaluation,
        error_type=(
            canvas_review.error_type
            if canvas_review is not None and canvas_review.error_type is not None
            else "UNKNOWN_ERROR"
            if state == "WRONG"
            else None
        ),
        intent="EXPRESSING_CONFUSION" if state == "STUCK" else "SUBMITTING_ANSWER",
        response_strategy=response_strategy,
        tutor_message=evaluation.tutor_message,
        tutor_message_voice_optimised=evaluation.tutor_message_voice,
        voice_optimised=True,
        hint_level=None,
        scaffold_steps_delivered=[],
        visual_cue=VisualCue(show=False, cue_type=None, description=None),
        canvas_feedback=(
            canvas_review.canvas_feedback
            if canvas_review is not None
            else CanvasFeedback(
                has_feedback=False,
                step_feedback=[],
                highlight_instruction=None,
            )
        ),
        mistake_classification=(
            canvas_review.mistake_classification
            if canvas_review is not None
            else None
        ),
        annotation_intents=(
            canvas_review.annotation_intents
            if canvas_review is not None
            else []
        ),
        next_phase_recommendation=request.current_phase,
        # Normal turns may refer to an answer the learner already supplied or
        # selected, but may not introduce a new final answer. The explicit
        # TutorSolved rescue path is the only authorised new-answer route.
        answer_reveal_allowed=(
            prompt_type_for_message(evaluation.tutor_message) == "SOURCE_CORRECTION"
            or guided_turn_has_answer_evidence(request, evaluation)
        ),
        confidence=evaluation.confidence,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        safety_check=safety_check,
        guardrail_check=GuardrailCheck(
            passed=True,
            violation_type=None,
            action_taken=None,
        ),
        student_model_events=[],
        attempt_increment=1 if state in {"CORRECT", "WRONG"} else 0,
        recommended_conversation_action=(
            "ADVANCE_TO_NEXT_QUESTION"
            if state == "CORRECT"
            else "REQUEST_EXPLANATION"
            if state == "PARTIAL"
            else "REQUEST_CLARIFICATION"
            if state == "UNCLEAR"
            else "ASK_QUESTION"
        ),
        question_completed=state == "CORRECT",
        answer_value_confirmed=(
            state == "CORRECT"
            or (
                objective is not None
                and "GENERAL_RULE" in objective.confirmed_concept_ids
            )
        ),
        reasoning_complete=state == "CORRECT",
        guided_student_state=state,
        selected_error_code=evaluation.selected_error_code,
        generated_question_rubric=rubric,
        active_teaching_objective=objective,
        guided_teaching_state=teaching_state_for(
            request,
            rubric,
            objective,
            evaluation.tutor_message,
        ),
        canvas_intentions=evaluation.canvas_intentions,
    )
    guarded_response = apply_answer_reveal_guardrail(
        response,
        request.correct_answer,
        rules,
    )
    if not requires_written_symbolic_rule_evidence(request, state):
        return guarded_response
    write_instruction = safe_guided_write_instruction(
        evaluation,
        request,
        rules,
    )
    message = write_instruction or (
        rules.guided_learning.critical_thinking.written_rule_prompt
    )
    return guarded_response.model_copy(
        update={
            "evaluation": "PARTIALLY_CORRECT",
            "response_strategy": "CLARIFY",
            "tutor_message": message,
            "tutor_message_voice_optimised": message,
            "attempt_increment": 0,
            "recommended_conversation_action": "REQUEST_CLARIFICATION",
            "question_completed": False,
            "answer_value_confirmed": True,
            "reasoning_complete": False,
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": request.active_teaching_objective,
            "guided_teaching_state": request.guided_teaching_state,
            "requires_written_math_evidence": True,
            "write_instruction": write_instruction,
        }
    )


def safe_guided_write_instruction(
    evaluation: GuidedEvaluation,
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> str | None:
    """Keep an evaluator-authored writing prompt from disclosing the rule."""

    if evaluation.write_instruction is None:
        return None
    instruction = evaluation.write_instruction.strip()
    if instruction == "":
        return None
    if contains_answer_reveal(instruction, request.correct_answer, rules):
        logger.warning(
            "guided_write_instruction_rejected",
            extra={"question_id": request.question_id, "reason": "answer_reveal"},
        )
        return None
    return instruction


def build_openai_ai_engine_client(settings: Settings) -> OpenAIAIEngineClient | None:
    if settings.use_openai_ai_engine is False:
        return None
    if settings.openai_api_key == "":
        return None
    from app.ai_engine.openai_client import OpenAIAIEngineClient
    rules = load_classifier_rules()

    return OpenAIAIEngineClient(
        api_key=settings.openai_api_key,
        model=settings.openai_ai_engine_model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        prompt_cache_key_enabled=settings.openai_prompt_cache_key_enabled,
        store_responses=settings.openai_store_responses,
        retry_count=settings.adapter_request_retry_count,
        guided_reasoning_effort=rules.guided_learning.reasoning_effort,
        guided_verbosity=rules.guided_learning.verbosity,
    )


def openai_model_for_request(
    settings: Settings,
    request: ClassificationRequest,
) -> str:
    """Choose the configured model for Guided Practice before any experiment arm."""

    if request.current_phase == "GUIDED_PRACTICE":
        return load_classifier_rules().guided_learning.model

    candidate = settings.openai_ai_engine_experiment_model.strip()
    percentage = settings.openai_ai_engine_experiment_percentage
    subject = request.experiment_subject_id
    if (
        candidate == ""
        or percentage == 0
        or subject is None
        or request.current_phase != "GUIDED_PRACTICE"
    ):
        return settings.openai_ai_engine_model
    bucket = int(hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < percentage:
        return candidate
    return settings.openai_ai_engine_model


def generate_explain_again_response(
    request: ExplainAgainRequest,
) -> ExplainAgainResult:
    """Generate wording for an explicit Explain Again turn without changing state."""

    rules = load_classifier_rules()
    validate_explain_again_request(request)
    settings = get_settings().model_copy(
        update={"openai_ai_engine_model": rules.guided_learning.model}
    )
    openai_client = build_openai_ai_engine_client(settings)
    if openai_client is None:
        raise AdapterError(
            "openai_ai_engine",
            "Explain Again requires an enabled OpenAI AI-engine client.",
        )

    last_error: AdapterError | None = None
    validation_feedback: str | None = None
    answer_reveal_rejected = False
    for attempt in range(rules.guided_learning.guided_turn_maximum_retries + 1):
        recent_conversation = request.recent_conversation[
            -rules.guided_learning.maximum_recent_history_turns:
        ] if rules.guided_learning.maximum_recent_history_turns > 0 else []
        prompt_request = request.model_copy(
            update={"recent_conversation": recent_conversation}
        )
        try:
            message = openai_client.generate_explain_again_message(
                request=prompt_request,
                validation_feedback=validation_feedback,
                prompt_version=rules.guided_learning.explain_again_prompt_version,
                system_prompt=rules.guided_learning.explain_again_system_prompt,
            )
        except AdapterError as error:
            last_error = error
            logger.warning(
                "explain_again_generation_retry",
                extra={
                    "question_id": request.question_id,
                    "attempt": attempt + 1,
                    "detail": error.detail,
                },
            )
            continue
        if request.answer_reveal_allowed or (
            message.answer_reveal_risk is False
            and not message_reveals_answer(
            message.tutor_message,
            message.tutor_message_voice_optimised,
            request.answer_spec.canonical_answer,
            rules,
            )
        ):
            return _explain_again_result(
                request,
                message.tutor_message,
                message.tutor_message_voice_optimised,
                message.confidence,
            )
        answer_reveal_rejected = True
        validation_feedback = (
            f"{rules.answer_reveal_guardrail.rewrite_feedback} "
            "Guardrail retry mode: return exactly one Socratic question that "
            "asks the student to supply the unresolved fact. Do not state, "
            "summarise, or paraphrase any answer component."
        )
        last_error = AdapterError(
            "openai_ai_engine",
            (
                "Explain Again response disclosed the final answer for "
                f"question_id={request.question_id}."
            ),
        )
        logger.warning(
            "explain_again_answer_reveal_retry",
            extra={"question_id": request.question_id, "attempt": attempt + 1},
        )
    if answer_reveal_rejected:
        safe_message = _safe_explain_again_message(request)
        logger.warning(
            "explain_again_safe_response_used",
            extra={"question_id": request.question_id},
        )
        return _explain_again_result(
            request,
            safe_message,
            safe_message,
            1.0,
        )
    raise last_error or AdapterError(
        "openai_ai_engine",
        f"Explain Again generation failed for question_id={request.question_id}.",
    )


def _explain_again_result(
    request: ExplainAgainRequest,
    tutor_message: str,
    tutor_message_voice_optimised: str,
    confidence: float,
) -> ExplainAgainResult:
    return ExplainAgainResult(
        interaction_type="EXPLAIN_AGAIN",
        tutor_message=tutor_message,
        tutor_message_voice_optimised=tutor_message_voice_optimised,
        confidence=confidence,
        attempt_increment=0,
        evaluation_reason_code="EXPLAIN_AGAIN_REEXPRESSION",
        guided_student_state=request.guided_student_state,
        active_teaching_objective=request.active_teaching_objective,
        first_unresolved_concept_id=request.first_unresolved_concept_id,
        selected_error_code=request.selected_error_code,
        support_served_this_turn=None,
        active_support_level=request.active_support_level,
        highest_support_used=request.highest_support_used,
        active_scaffold=request.active_scaffold,
        progression_change_requested=False,
    )


def _safe_explain_again_message(request: ExplainAgainRequest) -> str:
    if request.active_scaffold is not None:
        return (
            "Let’s look at the step already on your screen in a different way. "
            "What do you notice first?"
        )
    if request.visible_visual_cue is not None and request.visible_visual_cue.show:
        return (
            "Let’s use the visual already on your screen. "
            "What is the first difference you notice?"
        )
    return (
        "Let’s break the question into one smaller part. "
        "What information would you start with?"
    )


def validate_explain_again_request(request: ExplainAgainRequest) -> None:
    required_components = [
        component
        for component in request.generated_question_rubric.required_concepts
        if component.required
    ]
    component_ids = [component.concept_id for component in required_components]
    if request.generated_question_rubric.question_id != request.question_id:
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again rubric does not match question_id={request.question_id}.",
        )
    if len(component_ids) != len(set(component_ids)):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again requires unique runtime component IDs for {request.question_id}.",
        )
    required_ids = set(component_ids)
    if not required_ids:
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again requires at least one runtime required component for {request.question_id}.",
        )
    active_ids = {
        *request.active_teaching_objective.target_concept_ids,
        *request.active_teaching_objective.confirmed_concept_ids,
        *request.active_teaching_objective.missing_concept_ids,
    }
    if not active_ids.issubset(required_ids):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again objective has unknown runtime component IDs for {request.question_id}.",
        )
    if set(request.active_teaching_objective.confirmed_concept_ids) & set(
        request.active_teaching_objective.missing_concept_ids
    ):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again objective overlaps confirmed and missing components for {request.question_id}.",
        )
    if request.first_unresolved_concept_id not in set(
        request.active_teaching_objective.missing_concept_ids
    ):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again first unresolved component is not missing for {request.question_id}.",
        )
    objective_ids = {
        *request.active_teaching_objective.confirmed_concept_ids,
        *request.active_teaching_objective.missing_concept_ids,
    }
    if objective_ids != required_ids:
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again objective omits runtime required components for {request.question_id}.",
        )
    first_missing = next(
        component
        for component in required_components
        if component.concept_id in request.active_teaching_objective.missing_concept_ids
    )
    if request.first_unresolved_concept_id != first_missing.concept_id:
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again first unresolved component is out of runtime rubric order for {request.question_id}.",
        )
    if (request.selected_error_code is None) != (
        request.recorded_misconception is None
    ):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again selected error and recorded misconception must both be present or absent for {request.question_id}.",
        )
    if request.recorded_misconception is not None and (
        request.recorded_misconception.error_code != request.selected_error_code
    ):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again misconception does not match selected error for {request.question_id}.",
        )
    support_rank = {
        "NONE": 0,
        "HINT": 1,
        "VISUAL_CUE": 2,
        "SCAFFOLD": 3,
        "PARALLEL_EXAMPLE": 4,
        "TUTOR_SOLVED": 5,
    }
    if support_rank[request.active_support_level] > support_rank[
        request.highest_support_used
    ]:
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again active support exceeds highest support for {request.question_id}.",
        )
    if request.active_scaffold is not None and (
        request.active_scaffold.step_number > request.active_scaffold.total_steps
    ):
        raise AdapterError(
            "openai_ai_engine",
            f"Explain Again scaffold step exceeds total steps for {request.question_id}.",
        )


def generate_tutor_turn_with_openai(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
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
            answer_spec=request.answer_spec,
            phase_2_prompt_context=request.phase_2_prompt_context,
            active_triggers=detect_protocol_triggers(request, rules),
            student_input=request.student_input,
            phase=request.current_phase,
            input_source=request.input_source,
            transcript_confidence=request.transcript_confidence,
            attempt_count=request.attempt_count,
            current_hint_level=request.current_hint_level,
            question_completed=request.question_completed,
            answer_value_confirmed=request.answer_value_confirmed,
            reasoning_required=is_reasoning_required(request, rules),
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


def detect_protocol_triggers(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> list[Trigger]:
    triggers: list[Trigger] = []
    if (
        request.input_source == "VOICE"
        and is_low_confidence(request.transcript_confidence, rules)
    ):
        triggers.append(Trigger.VOICE_AMBIGUITY)
    if (
        request.input_source == "CANVAS"
        and request.canvas_regions
        and any(
            region.confidence < rules.canvas_review.min_region_confidence
            for region in request.canvas_regions
        )
    ):
        triggers.append(Trigger.HANDWRITING_AMBIGUITY)
    return triggers


def should_use_deterministic_tutor_turn(
    request: ClassificationRequest,
    intent: IntentType,
    rules: ClassifierRulesConfig,
) -> bool:
    if evaluate_answer_contract(request) == "CORRECT":
        return True
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
    authoritative_verification: bool,
    openai_turn: OpenAITutorTurn,
) -> TutorDecision:
    intent = (
        deterministic_intent
        if (
            deterministic_intent != "SUBMITTING_ANSWER"
            or deterministic_evaluation == "CORRECT"
        )
        else openai_turn.intent
    )
    evaluation = (
        deterministic_evaluation
        if (
            deterministic_intent != "SUBMITTING_ANSWER"
            or authoritative_verification
        )
        else (
            "CORRECT"
            if deterministic_evaluation == "CORRECT"
            else openai_turn.evaluation
        )
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
        reasoning_complete=(
            has_reasoning_evidence(request, rules)
            and (
                deterministic_evaluation == "CORRECT"
                or request.answer_value_confirmed
                or openai_turn.reasoning_complete
            )
        ),
    )


def build_tutor_message_with_openai(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
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

    rejected_message: str | None = None
    validation_feedback: str | None = None
    for attempt in range(rules.guided_learning.maximum_retries + 1):
        try:
            message = openai_client.build_tutor_message(
                question=request.question,
                student_input=request.student_input,
                evaluation=evaluation,
                error_type=error_type,
                response_strategy=response_strategy,
                hint_level=hint_level,
                phase=request.current_phase,
                conversation_history=request.conversation_history,
                canvas_context=canvas_context,
                support_context=None,
                rejected_tutor_message=rejected_message,
                validation_feedback=validation_feedback,
            )
        except AdapterError as error:
            logger.warning(
                "openai_ai_engine_fallback",
                extra={"step": "tutor_message", "detail": error.message},
            )
            return None
        if not message_reveals_answer(
            message.tutor_message,
            message.tutor_message_voice_optimised,
            request.correct_answer,
            rules,
        ):
            return message
        rejected_message = message.tutor_message
        validation_feedback = rules.answer_reveal_guardrail.rewrite_feedback
        logger.warning(
            "tutor_message_answer_reveal_retry",
            extra={
                "question_id": request.question_id,
                "attempt": attempt + 1,
                "input_source": request.input_source,
            },
        )
    return None


def build_support_aware_tutor_message(
    question_id: str | None,
    question: str,
    correct_answer: str,
    student_input: str,
    evaluation: EvaluationCategory | None,
    error_type: ErrorType | None,
    response_strategy: ResponseStrategy,
    hint_level: HintLevel | None,
    conversation_history: list[ConversationMessage],
    support_context: dict[str, object],
    openai_client: OpenAIAIEngineClient | None,
) -> OpenAITutorMessage | None:
    """Write a response that explicitly connects an authored support item to a turn."""

    if openai_client is None:
        return None
    rules = load_classifier_rules()
    rejected_message: str | None = None
    validation_feedback: str | None = None
    for attempt in range(rules.guided_learning.maximum_retries + 1):
        try:
            message = openai_client.build_tutor_message(
                question=question,
                student_input=student_input,
                evaluation=evaluation,
                error_type=error_type,
                response_strategy=response_strategy,
                hint_level=hint_level,
                phase="GUIDED_PRACTICE",
                conversation_history=conversation_history,
                canvas_context=None,
                support_context=support_context,
                rejected_tutor_message=rejected_message,
                validation_feedback=validation_feedback,
            )
        except AdapterError as error:
            logger.warning(
                "support_aware_tutor_message_fallback",
                extra={"question_id": question_id, "detail": error.message},
            )
            return None
        if not message_reveals_answer(
            message.tutor_message,
            message.tutor_message_voice_optimised,
            correct_answer,
            rules,
        ):
            return message
        rejected_message = message.tutor_message
        validation_feedback = rules.answer_reveal_guardrail.rewrite_feedback
        logger.warning(
            "support_aware_tutor_message_answer_reveal_retry",
            extra={"question_id": question_id, "attempt": attempt + 1},
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
    if any(
        re.search(pattern, normalized_input)
        for pattern in rules.guided_learning.semantic_confusion_patterns
    ):
        return "EXPRESSING_CONFUSION"
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
    contract_evaluation = evaluate_answer_contract(request)
    if contract_evaluation is not None:
        return contract_evaluation
    if is_voice_value_only_correct(request, rules):
        return "CORRECT"
    if is_value_only_correct(request):
        return "PARTIALLY_CORRECT"
    if is_correct_answer(request, rules):
        return "CORRECT"
    if has_visible_correct_method(normalized_input, rules):
        return "PARTIALLY_CORRECT"

    return "INCORRECT"


_AUTHORITATIVE_VERIFICATION_METHODS: frozenset[str] = frozenset(
    {
        "EXACT_CHOICE_MATCH",
        "EXACT_NOTATION_MATCH",
        "SYMBOLIC_EQUIVALENCE",
    }
)
_SUPERSCRIPT_CHARACTERS: dict[str, str] = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
}
_FRACTION_CHARACTERS: dict[str, str] = {
    "½": "1/2",
    "⅓": "1/3",
    "¼": "1/4",
    "¾": "3/4",
    "⅔": "2/3",
    "⅛": "1/8",
}


def uses_authoritative_verification(request: ClassificationRequest) -> bool:
    return (
        request.answer_spec is not None
        and request.answer_spec.verification_method
        in _AUTHORITATIVE_VERIFICATION_METHODS
    )


def evaluate_answer_contract(
    request: ClassificationRequest,
) -> EvaluationCategory | None:
    answer_spec = request.answer_spec
    if answer_spec is None:
        return None
    method = answer_spec.verification_method
    accepted_answers = [
        answer_spec.canonical_answer,
        *answer_spec.accepted_answers,
    ]
    if method == "EXACT_CHOICE_MATCH":
        student_choice = normalized_choice_response(request.student_input)
        accepted_choices = {answer.strip().upper() for answer in accepted_answers}
        return "CORRECT" if student_choice in accepted_choices else "INCORRECT"
    if method == "EXACT_NOTATION_MATCH":
        student_notation = normalize_exact_notation(request.student_input)
        accepted_notation = {
            normalize_exact_notation(answer)
            for answer in accepted_answers
        }
        return (
            "CORRECT"
            if student_notation in accepted_notation
            or contains_accepted_exact_notation(
                request.student_input,
                accepted_notation,
            )
            else "INCORRECT"
        )
    if method == "SYMBOLIC_EQUIVALENCE":
        return (
            "CORRECT"
            if is_symbolically_equivalent(request.student_input, accepted_answers)
            else "INCORRECT"
        )
    normalized_input = normalize_semantic_answer(request.student_input)
    concept_required_methods = {
        "CHOICE_AND_CONCEPT_MATCH",
        "BOOLEAN_AND_CONCEPT_MATCH",
    }
    if (
        normalized_input == normalize_semantic_answer(
            answer_spec.canonical_answer
        )
        and method not in concept_required_methods
    ):
        return "CORRECT"
    if (
        method == "CONCEPT_TEXT_MATCH"
        and ";" not in answer_spec.canonical_answer
        and normalized_input
        in {
            normalize_semantic_answer(answer)
            for answer in answer_spec.accepted_answers
        }
    ):
        return "CORRECT"
    return None


def normalized_choice_response(student_input: str) -> str:
    """Return the selected option ID from a short typed choice response."""

    normalized = student_input.strip().upper()
    match = re.fullmatch(
        r"(?:I\s+(?:CHOOSE|CHOSE)\s+(?:OPTION\s+)?|(?:THE\s+)?(?:OPTION|CHOICE)\s+)?([A-Z])\.?",
        normalized,
    )
    return match.group(1) if match is not None else normalized


def normalize_exact_notation(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    result: list[str] = []
    index = 0
    while index < len(normalized):
        character = normalized[index]
        if character in _SUPERSCRIPT_CHARACTERS:
            digits: list[str] = []
            while (
                index < len(normalized)
                and normalized[index] in _SUPERSCRIPT_CHARACTERS
            ):
                digits.append(_SUPERSCRIPT_CHARACTERS[normalized[index]])
                index += 1
            result.extend(("^", "".join(digits)))
            continue
        result.append(character)
        index += 1
    compact = "".join(result).replace("−", "-").replace("⁄", "/")
    for fraction, expanded in _FRACTION_CHARACTERS.items():
        compact = compact.replace(fraction, expanded)
    compact = re.sub(r"\s+", "", compact)
    compact = re.sub(r"\((\d+/\d+)\)(?=[A-Za-z])", r"\1", compact)
    return re.sub(r"\^\{(\d+)\}", r"^\1", compact)


def contains_accepted_exact_notation(
    student_input: str,
    accepted_notation: set[str],
) -> bool:
    normalized_input = _normalize_superscript_notation(student_input)
    for notation in accepted_notation:
        if notation == "":
            continue
        spaced_notation = r"\s*".join(re.escape(character) for character in notation)
        start_boundary = r"(?<!\w)" if notation[0].isalnum() else ""
        end_boundary = r"(?!\w)" if notation[-1].isalnum() else ""
        if re.search(
            f"{start_boundary}{spaced_notation}{end_boundary}",
            normalized_input,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def _normalize_superscript_notation(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    for superscript, digit in _SUPERSCRIPT_CHARACTERS.items():
        normalized = normalized.replace(superscript, f"^{digit}")
    normalized = normalized.replace("−", "-").replace("⁄", "/")
    return re.sub(r"\^\{(\d+)\}", r"^\1", normalized)


def normalize_semantic_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    normalized = normalized.replace("⁄", "/").replace("−", "-")
    normalized = re.sub(
        r"\b(?:is\s+)?multiplied\s+by\b|\btimes\b|\bmultiply\s+by\b",
        " multiply ",
        normalized,
    )
    normalized = re.sub(r"\bdivided\s+by\b|\bdivide\s+by\b", " divide ", normalized)
    normalized = re.sub(r"\bplus\b", " add ", normalized)
    normalized = re.sub(r"\bminus\b", " subtract ", normalized)
    normalized = re.sub(r"\bis\s+equal\s+to\b|\bequals?\b", " equal ", normalized)
    normalized = re.sub(r"(?<=\w)\s+x\s+(?=\w)", " multiply ", normalized)
    normalized = re.sub(r"[×·*]", " multiply ", normalized)
    normalized = normalized.replace("÷", " divide ")
    normalized = normalized.replace("/", " divide ")
    normalized = normalized.replace("+", " add ")
    normalized = normalized.replace("-", " subtract ")
    normalized = normalized.replace("=", " equal ")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def is_symbolically_equivalent(
    student_input: str,
    accepted_answers: list[str],
) -> bool:
    from sympy import Symbol, simplify, sympify

    allowed_pattern = r"[A-Za-z0-9+\-*/^().\s]+"
    normalized_student = normalize_compact_spoken_expression(student_input)
    candidates = [normalized_student]
    candidates.extend(
        match.group(0)
        for match in re.finditer(r"\b[A-Za-z]\s*[+\-*/]\s*\d+(?:\.\d+)?\b", normalized_student)
    )
    if not candidates or all(re.fullmatch(allowed_pattern, candidate) is None for candidate in candidates):
        return False
    for candidate in candidates:
        if re.fullmatch(allowed_pattern, candidate) is None:
            continue
        expressions = [candidate, *accepted_answers]
        symbol_names = set(re.findall(r"[A-Za-z]+", " ".join(expressions)))
        symbols = {name: Symbol(name) for name in symbol_names}
        try:
            student_expression = sympify(candidate.replace("^", "**"), locals=symbols)
            if any(
                simplify(
                    student_expression
                    - sympify(answer.replace("^", "**"), locals=symbols)
                )
                == 0
                for answer in accepted_answers
                if re.fullmatch(allowed_pattern, answer) is not None
            ):
                return True
        except (TypeError, ValueError, SyntaxError):
            continue
    return False


def normalize_compact_spoken_expression(value: str) -> str:
    """Turn unspaced spoken algebra such as ``NPlus5`` into safe notation."""

    normalized = unicodedata.normalize("NFKC", value).replace("−", "-")
    operations = {
        "plus": "+",
        "add": "+",
        "minus": "-",
        "subtract": "-",
        "times": "*",
        "multiply": "*",
        "dividedby": "/",
        "divide": "/",
    }
    for word, symbol in operations.items():
        normalized = re.sub(
            rf"\b([A-Za-z])\s*{word}\s*(-?\d+(?:\.\d+)?)\b",
            rf"\1 {symbol} \2",
            normalized,
            flags=re.IGNORECASE,
        )
    return normalized.casefold()


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
    if (
        intent == "EXPRESSING_CONFUSION"
        and current_phase == rules.strategy_rules.guided_practice_phase
    ):
        if attempt_count >= rules.strategy_rules.worked_example_min_attempt_count:
            return "PROVIDE_WORKED_EXAMPLE"
        if attempt_count >= rules.strategy_rules.scaffold_min_attempt_count:
            return "SCAFFOLD"
        return "GUIDED_HINT"
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
    canvas_review: CanvasMathReview | None = _canvas_review_for(
        request,
        rules,
        confidence,
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
    if (
        canvas_review is not None
        and canvas_review.mistake_classification.status == "no_mistake"
        and request.canvas_solution_complete_candidate
    ):
        effective_evaluation = "CORRECT"
    elif (
        canvas_review is not None
        and canvas_review.mistake_classification.status == "mistake_found"
    ):
        effective_evaluation = "INCORRECT"
    if canvas_mistake_found and evaluation == "CORRECT" and not request.has_canvas_evidence:
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
        reasoning_complete=has_reasoning_evidence(request, rules),
    )


def _canvas_review_for(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
    confidence: float,
) -> CanvasMathReview | None:
    """Review Canvas evidence for every tutor path that may annotate submitted work."""

    if not request.has_canvas_evidence and request.input_source != "CANVAS":
        return None
    return review_canvas_math(
        question=request.question,
        correct_answer=canvas_expected_answer(request),
        current_phase=request.current_phase,
        canvas_regions=request.canvas_regions,
        spatial_tokens=request.spatial_tokens,
        config=rules.canvas_review,
        confidence=confidence,
    )


def canvas_expected_answer(request: ClassificationRequest) -> str:
    """Select the authored component that the current Canvas turn answers."""

    rubric = request.generated_question_rubric
    if rubric is None:
        return request.correct_answer

    component_id = (
        request.guided_teaching_state.active_component_id
        if request.guided_teaching_state is not None
        else active_component_id(rubric, request.active_teaching_objective)
    )
    if component_id is None:
        return request.correct_answer

    component_index: int | None = next(
        (
            index
            for index, component in enumerate(rubric.required_concepts)
            if component.concept_id == component_id
        ),
        None,
    )
    if component_index is None:
        return request.correct_answer

    component_description: str = next(
        component.description.strip()
        for component in rubric.required_concepts
        if component.concept_id == component_id
    )
    answer_parts: list[str] = [
        part.strip() for part in request.correct_answer.split(";")
    ]
    if component_index < len(answer_parts) and _looks_like_canvas_expression(
        answer_parts[component_index]
    ):
        return answer_parts[component_index]

    component_expression: str | None = _canvas_expression_from_description(
        component_description
    )
    canonical_text: str = normalize_canvas_math_text(request.correct_answer).replace(
        " ", ""
    )
    component_text: str = normalize_canvas_math_text(component_expression or "").replace(
        " ", ""
    )
    if (
        component_expression is not None
        and re.search(
            rf"{re.escape(component_text)}(?![A-Za-z0-9.])",
            canonical_text,
        )
        is not None
    ):
        return component_expression

    if component_index < len(answer_parts):
        return answer_parts[component_index]
    return request.correct_answer


def _looks_like_canvas_expression(text: str) -> bool:
    expression: str = _CANVAS_LATEX_COMMAND.sub("", text)
    return (
        _CANVAS_EXPRESSION.fullmatch(expression) is not None
        and re.search(r"[A-Za-z]{2,}", expression) is None
    )


def _canvas_expression_from_description(text: str) -> str | None:
    if _looks_like_canvas_expression(text):
        return text
    match = _CANVAS_EXPRESSION_FRAGMENT.search(text)
    return match.group(0) if match is not None else None


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
    reasoning_required: bool = is_reasoning_required(request, rules)
    answer_value_confirmed: bool = (
        request.answer_value_confirmed or decision.evaluation == "CORRECT"
    )
    reasoning_complete: bool = (
        not reasoning_required or decision.reasoning_complete
    )
    question_completed: bool = (
        request.question_completed
        or (
            answer_value_confirmed
            and reasoning_complete
            and decision.evaluation in {"CORRECT", "PARTIALLY_CORRECT"}
        )
    )
    explanation_required: bool = (
        reasoning_required
        and answer_value_confirmed
        and not question_completed
    )
    completed_reasoning_turn: bool = (
        request.answer_value_confirmed
        and question_completed
        and not request.question_completed
    )
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
    if explanation_required:
        tutor_message = (
            rules.reasoning_completion.explanation_reason_message
            if (
                request.answer_value_confirmed
                and has_operation_evidence(request, rules)
            )
            else rules.reasoning_completion.explanation_incomplete_message
            if request.answer_value_confirmed
            else rules.reasoning_completion.explanation_required_message
        )
        voice_message = tutor_message
    elif (
        reasoning_required
        and question_completed
        and not request.question_completed
    ):
        tutor_message = rules.reasoning_completion.explanation_accepted_message
        voice_message = tutor_message
    response_evaluation: EvaluationCategory | None = (
        "PARTIALLY_CORRECT"
        if explanation_required
        else "CORRECT"
        if completed_reasoning_turn
        else decision.evaluation
    )
    response_error_type: ErrorType | None = (
        "INSUFFICIENT_INFORMATION"
        if explanation_required
        else None
        if completed_reasoning_turn
        else decision.error_type
    )
    events: list[StudentModelEvent] = []
    if should_emit_student_model_event(decision) and not explanation_required:
        events = [
            build_student_model_event(
                response_evaluation,
                response_error_type,
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
        evaluation=response_evaluation,
        error_type=response_error_type,
        intent=decision.intent,
        response_strategy=(
            "CLARIFY" if explanation_required else decision.response_strategy
        ),
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
        attempt_increment=(
            0
            if request.answer_value_confirmed
            else select_attempt_increment(decision)
        ),
        recommended_conversation_action=(
            "REQUEST_EXPLANATION"
            if explanation_required
            else select_conversation_action(decision)
        ),
        question_completed=question_completed,
        answer_value_confirmed=answer_value_confirmed,
        reasoning_complete=reasoning_complete,
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
    if not message_reveals_answer(
        response.tutor_message,
        response.tutor_message_voice_optimised,
        correct_answer,
        rules,
    ):
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
    semantic_message = normalize_semantic_answer(message)
    semantic_correct_answer = normalize_semantic_answer(correct_answer)

    correct_numbers: list[str] = re.findall(r"-?\d+(?:\.\d+)?", correct_answer)
    is_bare_numeric_answer = (
        len(correct_numbers) == 1
        and re.fullmatch(r"-?\d+(?:\.\d+)?", normalized_correct_answer) is not None
    )
    exact_answer_present = False
    if not is_bare_numeric_answer and len(normalized_correct_answer) == 1 and normalized_correct_answer.isalnum():
        exact_answer_present = (
            re.search(
                rf"(?<!\w){re.escape(normalized_correct_answer)}(?!\w)",
                normalized_message,
            )
            is not None
        )
    elif not is_bare_numeric_answer and normalized_correct_answer != "":
        exact_answer_present = normalized_correct_answer in normalized_message
    if (
        len(semantic_correct_answer.split()) > 1
        and semantic_correct_answer in semantic_message
    ):
        exact_answer_present = True
    if exact_answer_present:
        return True
    if contains_any(normalized_message, rules.answer_reveal_guardrail.reveal_phrases):
        return True
    is_single_numeric_answer = (
        len(correct_numbers) == 1
        and (
            re.search(r"[a-z]", semantic_correct_answer) is None
            or re.fullmatch(r"[a-z]\s*=\s*-?\d+(?:\.\d+)?", correct_answer.casefold().strip())
            is not None
        )
    )
    if not is_single_numeric_answer:
        return False

    correct_value: float = float(correct_numbers[0])
    explicit_numeric_reveal = re.search(
        r"\b(?:the\s+)?(?:final\s+)?answer\s+(?:is|equals)\b|"
        r"\btherefore\b|\bso\s+the\s+answer\b|\b(?:gives|equals)\s+-?\d",
        normalized_message,
    )
    if explicit_numeric_reveal is None:
        return False
    message_numbers: list[str] = re.findall(r"-?\d+(?:\.\d+)?", normalized_message)
    return any(float(value) == correct_value for value in message_numbers)


def message_reveals_answer(
    message: str,
    voice_message: str,
    correct_answer: str,
    rules: ClassifierRulesConfig,
) -> bool:
    return contains_answer_reveal(
        message,
        correct_answer,
        rules,
    ) or contains_answer_reveal(
        voice_message,
        correct_answer,
        rules,
    )


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


def is_reasoning_required(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    if (
        request.answer_spec is not None
        and request.answer_spec.verification_method == "CONCEPT_TEXT_MATCH"
        and evaluate_answer_contract(request) == "CORRECT"
    ):
        return False
    if (
        request.answer_spec is not None
        and request.answer_spec.explanation_required is not None
    ):
        return request.answer_spec.explanation_required
    if uses_authoritative_verification(request):
        return False
    return request.current_phase in rules.reasoning_completion.required_phases


def has_reasoning_evidence(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    if request.input_source == "CANVAS":
        readable_steps = [
            region
            for region in request.canvas_regions
            if region.text.strip() != ""
        ]
        return (
            len(readable_steps)
            >= rules.reasoning_completion.minimum_canvas_steps
        )

    student_evidence: list[str] = [
        message.content
        for message in request.conversation_history
        if message.role == "user"
    ]
    student_evidence.append(request.student_input)
    normalized_input: str = normalize_text(" ".join(student_evidence))
    explanation_words: list[str] = normalized_input.split()
    if (
        len(explanation_words)
        >= rules.reasoning_completion.minimum_explanation_words
        and contains_any(
            normalized_input,
            rules.reasoning_completion.explanation_terms,
        )
    ):
        return True
    return normalized_input.count("=") >= 2


def has_operation_evidence(
    request: ClassificationRequest,
    rules: ClassifierRulesConfig,
) -> bool:
    return contains_any(
        normalize_text(request.student_input),
        rules.reasoning_completion.operation_terms,
    )


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
