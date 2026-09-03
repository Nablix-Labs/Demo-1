from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, StrictBool, model_validator

from app.ai_engine.schemas import ErrorType, IntentType, LearningPhase, ResponseStrategy, StrictSchema, VisualCueType
from app.models.guided_learning import GuidedStudentState
from app.models.student_model_session import QuestionType


CONFIG_PATH: Path = Path("configs/classifier_rules.yaml")


class ConfidenceConfig(StrictSchema):
    safety_response: float = Field(ge=0.0, le=1.0)
    standard_response: float = Field(ge=0.0, le=1.0)


class SafetyConfig(StrictSchema):
    unsafe_terms: list[str]
    flag_type: str
    action_taken: str


class AnswerPatternsConfig(StrictSchema):
    answer_notation: list[str]
    no_attempt: list[str]
    ambiguous: list[str]
    correct_method: list[str]
    spoken_number_values: dict[str, float]


class ErrorPatternsConfig(StrictSchema):
    insufficient_information: list[str]
    unknown_error: list[str]


class SignErrorCaseConfig(StrictSchema):
    question: str
    student_value: float
    correct_value: float


class NumericErrorCaseConfig(StrictSchema):
    question: str
    student_value: float


class ProceduralErrorCaseConfig(StrictSchema):
    question: str
    phrases: list[str]


class DiagnosticCasesConfig(StrictSchema):
    sign_error: SignErrorCaseConfig
    opposite_operation_error: NumericErrorCaseConfig
    conceptual_misunderstanding: NumericErrorCaseConfig
    procedural_error: ProceduralErrorCaseConfig


class StrategyRulesConfig(StrictSchema):
    clarify_intents: list[IntentType]
    hint_intent: IntentType
    diagnostic_phase: LearningPhase
    concept_orientation_phase: LearningPhase
    review_phase: LearningPhase
    guided_practice_phase: LearningPhase
    independent_practice_phase: LearningPhase
    stuck_scaffold_min_count: int = Field(ge=1)
    scaffold_min_attempt_count: int = Field(ge=1)
    worked_example_min_attempt_count: int = Field(ge=1)


class ScaffoldResponseRulesConfig(StrictSchema):
    aliases: dict[str, list[str]]


class VisualCueRuleConfig(StrictSchema):
    cue_type: VisualCueType
    description: str


class VisualCueRulesConfig(StrictSchema):
    enabled_response_strategies: list[ResponseStrategy]
    enabled_phases: list[LearningPhase]
    cues: dict[ErrorType, VisualCueRuleConfig]


class AnswerRevealGuardrailConfig(StrictSchema):
    direct_request_phrases: list[str]
    override_phrases: list[str]
    reveal_phrases: list[str]
    rewrite_feedback: str
    safe_message: str
    flag_type: str
    action_taken: str


class ConversationRulesConfig(StrictSchema):
    max_recent_messages: int = Field(ge=0)
    acknowledgement_phrases: list[str]


class ReasoningCompletionConfig(StrictSchema):
    required_phases: list[LearningPhase]
    explanation_terms: list[str]
    operation_terms: list[str]
    minimum_explanation_words: int = Field(ge=2)
    minimum_canvas_steps: int = Field(ge=2)
    explanation_required_message: str
    explanation_incomplete_message: str
    explanation_reason_message: str
    explanation_accepted_message: str


class IndependentPracticeConfig(StrictSchema):
    answer_recorded_message: str
    rescue_required_message: str
    awaiting_submission_message: str
    input_unclear_message: str


class CanvasReviewMessagesConfig(StrictSchema):
    ARITHMETIC_ERROR: str
    SIGN_ERROR: str
    OPPOSITE_OPERATION_ERROR: str
    CONCEPTUAL_MISUNDERSTANDING: str
    PROCEDURAL_ERROR: str
    downstream_step: str


class CanvasReviewConfig(StrictSchema):
    min_region_confidence: float = Field(ge=0.0, le=1.0)
    max_expression_characters: int = Field(ge=1)
    feedback_enabled_phases: list[LearningPhase]
    annotation_enabled_phases: list[LearningPhase]
    semantic_localization_enabled: StrictBool
    messages: CanvasReviewMessagesConfig


class MessageConfig(StrictSchema):
    SAFETY_RESPONSE: str
    REQUESTING_ANSWER_OR_OVERRIDE: str
    REQUESTING_HINT: str
    EXPRESSING_CONFUSION: str
    OFF_TOPIC: str
    CORRECT: str
    UNCLEAR: str
    NO_ATTEMPT: str
    IRRELEVANT: str
    ARITHMETIC_ERROR: str
    SIGN_ERROR: str
    OPPOSITE_OPERATION_ERROR: str
    CONCEPTUAL_MISUNDERSTANDING: str
    PROCEDURAL_ERROR: str
    NOTATION_ISSUE: str
    INSUFFICIENT_INFORMATION: str
    DEFAULT: str
    QUESTION_COMPLETE_ACKNOWLEDGEMENT: str
    CONTEXTUAL_ACKNOWLEDGEMENT: str
    QUESTION_ALREADY_COMPLETE: str
    NEXT_QUESTION: str
    SCAFFOLD_STEP_RETRY: str
    SCAFFOLD_ORIGINAL_RETRY: str


class GuidedStateMappingConfig(StrictSchema):
    student_model_event: str | None
    strategy: str | None


class FallbackCanvasLabelsConfig(StrictSchema):
    changing_value: str
    fixed_value: str
    operation: str
    generic: str
    operation_names: dict[str, str]


class CanvasRescueWordingConfig(StrictSchema):
    parallel_step_suffix: str
    parallel_final_suffix: str
    tutor_solved_step_suffix: str
    tutor_solved_final_suffix: str
    tutor_solved_return_focus_text: str


class CriticalThinkingConfig(StrictSchema):
    """Configuration for controller-owned critical-thinking moves."""

    distress_phrases: list[str]
    frustration_phrases: list[str]
    distress_message: str
    frustration_acknowledgement: str
    ambiguity_message: str
    confusion_teaching_probe: str
    confusion_choice_teaching_probe: str
    repeated_confusion_scaffold_message: str
    confusion_phrases: list[str]
    wrong_choice_prompt: str
    wrong_direct_rule_prompt: str
    typed_option_prompt: str
    choice_selection_prompt: str
    choice_reasoning_prompt: str
    choice_reasoning_stuck_prompt: str
    variable_called_fixed_prompt: str
    fixed_value_called_changing_prompt: str
    fixed_value_sign_mismatch_prompt: str
    operation_direction_mismatch_prompt: str
    operation_called_value_prompt: str
    active_role_before_operation_prompt: str
    single_case_defence_prompt: str
    written_rule_prompt: str
    missing_operation_canvas_prompt: str
    missing_operation_canvas_llm_constraints: list[str]


class GuidedLearningConfig(StrictSchema):
    model: str
    model_supports_reasoning_effort: StrictBool
    single_call_enabled: StrictBool
    guided_turn_maximum_retries: int = Field(ge=0)
    scaffold_evaluation_maximum_retries: int = Field(ge=0)
    scaffold_evaluation_failure_message: str
    minimum_voice_transcript_confidence: float = Field(ge=0.0, le=1.0)
    minimum_ocr_confidence: float = Field(ge=0.0, le=1.0)
    canvas_rescue_presentation_enabled: StrictBool
    canvas_rescue_wording: CanvasRescueWordingConfig
    evaluation_mode: str
    confidence_threshold: float = Field(ge=0.0, le=1.0)
    state_confidence_thresholds: dict[
        GuidedStudentState,
        Annotated[float, Field(ge=0.0, le=1.0)],
    ]
    maximum_retries: int = Field(ge=0)
    stuck_escalation_count: int = Field(ge=1)
    maximum_recent_history_turns: int = Field(ge=0)
    tutor_message_similarity_threshold: float = Field(ge=0.0, le=1.0)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"]
    verbosity: Literal["low", "medium", "high"]
    semantic_confusion_patterns: list[str]
    rubric_prompt_version: str
    evaluator_prompt_version: str
    component_adjudicator_prompt_version: str
    explain_again_prompt_version: str
    rubric_system_prompt: str
    evaluator_system_prompt: str
    fact_budget_wording_system_prompt: str
    component_adjudicator_system_prompt: str
    component_adjudicator_confidence_threshold: float = Field(ge=0.0, le=1.0)
    explain_again_system_prompt: str
    scaffold_evaluator_system_prompt: str
    answer_reveal_retry_feedback: str
    deterministic_follow_up_wording_feedback: str
    reconciliation_message: str
    general_rule_fixed_value_prompt: str
    general_rule_changing_value_prompt: str
    allowed_student_states: list[GuidedStudentState]
    supported_verification_methods: list[str]
    multi_component_question_types: list[QuestionType]
    llm_state_mapping: dict[GuidedStudentState, GuidedStateMappingConfig]
    fallback_canvas_labels: FallbackCanvasLabelsConfig
    critical_thinking: CriticalThinkingConfig

    @model_validator(mode="after")
    def require_state_confidence_thresholds(self) -> "GuidedLearningConfig":
        missing_states = set(self.allowed_student_states) - set(
            self.state_confidence_thresholds
        )
        if missing_states:
            raise ValueError(
                "Missing Guided Learning confidence thresholds for "
                f"{sorted(missing_states)}."
            )
        return self


class ClassifierRulesConfig(StrictSchema):
    low_transcript_confidence_threshold: float = Field(ge=0.0, le=1.0)
    confidence: ConfidenceConfig
    safety: SafetyConfig
    intent_phrases: dict[IntentType, list[str]]
    answer_patterns: AnswerPatternsConfig
    error_patterns: ErrorPatternsConfig
    diagnostic_cases: DiagnosticCasesConfig
    strategy_rules: StrategyRulesConfig
    scaffold_response_rules: ScaffoldResponseRulesConfig
    visual_cue_rules: VisualCueRulesConfig
    answer_reveal_guardrail: AnswerRevealGuardrailConfig
    conversation_rules: ConversationRulesConfig
    reasoning_completion: ReasoningCompletionConfig
    canvas_review: CanvasReviewConfig
    progressive_hint_messages: dict[ErrorType, list[str]]
    messages: MessageConfig
    guided_learning: GuidedLearningConfig
    independent_practice: IndependentPracticeConfig


@lru_cache(maxsize=1)
def load_classifier_rules() -> ClassifierRulesConfig:
    raw_config: object = yaml.safe_load(CONFIG_PATH.read_text())
    return ClassifierRulesConfig.model_validate(raw_config)
