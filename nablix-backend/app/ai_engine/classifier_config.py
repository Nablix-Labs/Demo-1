from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field

from app.ai_engine.schemas import ErrorType, IntentType, LearningPhase, ResponseStrategy, StrictSchema, VisualCueType


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
    scaffold_min_attempt_count: int = Field(ge=1)
    worked_example_min_attempt_count: int = Field(ge=1)


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
    safe_message: str
    flag_type: str
    action_taken: str


class ConversationRulesConfig(StrictSchema):
    max_recent_messages: int = Field(ge=0)
    acknowledgement_phrases: list[str]


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


class ClassifierRulesConfig(StrictSchema):
    low_transcript_confidence_threshold: float = Field(ge=0.0, le=1.0)
    confidence: ConfidenceConfig
    safety: SafetyConfig
    intent_phrases: dict[IntentType, list[str]]
    answer_patterns: AnswerPatternsConfig
    error_patterns: ErrorPatternsConfig
    diagnostic_cases: DiagnosticCasesConfig
    strategy_rules: StrategyRulesConfig
    visual_cue_rules: VisualCueRulesConfig
    answer_reveal_guardrail: AnswerRevealGuardrailConfig
    conversation_rules: ConversationRulesConfig
    canvas_review: CanvasReviewConfig
    progressive_hint_messages: dict[ErrorType, list[str]]
    messages: MessageConfig


@lru_cache(maxsize=1)
def load_classifier_rules() -> ClassifierRulesConfig:
    raw_config: object = yaml.safe_load(CONFIG_PATH.read_text())
    return ClassifierRulesConfig.model_validate(raw_config)
