from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.models.adapters import ConversationAction, ConversationMessage
from app.models.guided_learning import (
    ActiveTeachingObjective,
    GeneratedQuestionRubric,
    GuidedStudentState,
)
from app.models.student_model_session import SupportUsed


EvaluationCategory = Literal[
    "CORRECT",
    "PARTIALLY_CORRECT",
    "INCORRECT",
    "UNCLEAR",
    "NO_ATTEMPT",
    "IRRELEVANT",
]

ErrorType = Literal[
    "ARITHMETIC_ERROR",
    "SIGN_ERROR",
    "OPPOSITE_OPERATION_ERROR",
    "CONCEPTUAL_MISUNDERSTANDING",
    "PROCEDURAL_ERROR",
    "NOTATION_ISSUE",
    "INSUFFICIENT_INFORMATION",
    "UNKNOWN_ERROR",
]

IntentType = Literal[
    "SUBMITTING_ANSWER",
    "ASKING_QUESTION",
    "EXPRESSING_CONFUSION",
    "REQUESTING_HINT",
    "REQUESTING_ANSWER",
    "ATTEMPTING_OVERRIDE",
    "OFF_TOPIC",
    "ACKNOWLEDGEMENT",
]

ResponseStrategy = Literal[
    "GUIDED_HINT",
    "SCAFFOLD",
    "CLARIFY",
    "CONFIRM_CORRECT",
    "ENCOURAGE_RETRY",
    "PROVIDE_VISUAL_CUE",
    "PROVIDE_WORKED_EXAMPLE",
    "DIAGNOSTIC_PROMPT",
    "MASTERY_CONFIRM",
    "SAFETY_RESPONSE",
    "CONTINUE",
    "INDEPENDENT_RESCUE_REQUIRED",
]

InputSource = Literal["TEXT", "VOICE", "CANVAS"]
Phase3SubmissionKind = Literal["CANVAS", "CHOICE"]
IndependentOutcome = Literal[
    "INDEPENDENTLY_VERIFIED",
    "RESCUE_REQUIRED",
    "INPUT_UNCLEAR",
    "AWAITING_SUBMISSION",
]

LearningPhase = Literal[
    "DIAGNOSTIC",
    "CONCEPT_ORIENTATION",
    "GUIDED_PRACTICE",
    "INDEPENDENT_PRACTICE",
    "REVIEW",
]


LearningEventType = Literal[
    "CORRECT_ATTEMPT",
    "INCORRECT_ATTEMPT",
    "PARTIAL_ATTEMPT",
    "HINT_USED",
    "SCAFFOLD_STEP_DELIVERED",
    "VISUAL_CUE_SHOWN",
    "CANVAS_SUBMITTED",
    "SESSION_STARTED",
    "SESSION_ENDED",
    "PHASE_TRANSITION",
    "MASTERY_ACHIEVED",
    "SAFETY_FLAG",
    "VOICE_FALLBACK",
]

VisualCueType = Literal[
    "EQUATION_BLOCK",
    "NUMBER_LINE",
    "GRAPH",
    "TABLE",
    "HIGHLIGHTED_STEP",
    "CONCEPT_CARD",
]

CanvasStepEvaluation = Literal["CORRECT", "INCORRECT"]
HighlightType = Literal["ERROR"]
HighlightColour = Literal["RED"]
HintLevel = Literal[1, 2, 3]
MistakeStatus = Literal["mistake_found", "no_mistake", "uncertain"]
LocalizationStatus = Literal["validated", "uncertain", "not_applicable"]
SpatialMathTokenRole = Literal[
    "number",
    "operator",
    "identifier",
    "relation",
    "parenthesis",
    "other",
]
AnnotationIntentKind = Literal["circle_target", "write_correction", "draw_arrow"]
AnnotationPlacement = Literal["right", "below"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisualCue(StrictSchema):
    show: StrictBool
    cue_type: VisualCueType | None
    description: str | None
    actions: list[dict[str, object]] = Field(default_factory=list)


class HighlightInstruction(StrictSchema):
    step_number: int = Field(ge=1)
    highlight_type: HighlightType
    colour: HighlightColour


class CanvasStepFeedback(StrictSchema):
    step_number: int = Field(ge=1)
    evaluation: CanvasStepEvaluation
    error_type: ErrorType | None
    feedback: str | None


class CanvasFeedback(StrictSchema):
    has_feedback: StrictBool
    step_feedback: list[CanvasStepFeedback]
    highlight_instruction: HighlightInstruction | None


class CanvasTextRegion(StrictSchema):
    step_id: str | None
    text: str
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class SpatialMathToken(StrictSchema):
    """OCR token reference safe to include in an LLM localization request."""

    token_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    role: SpatialMathTokenRole
    alignment_confidence: float = Field(ge=0.0, le=1.0)


class CanvasTokenDiagnosis(StrictSchema):
    status: MistakeStatus
    mistake_step_id: str | None
    target_token_ids: list[str]
    error_token: str | None
    expected_token: str | None
    error_type: ErrorType | None
    confidence: float = Field(ge=0.0, le=1.0)


class AuthoredErrorDefinition(StrictSchema):
    error_code: str = Field(pattern=r"^ERR-[A-Z0-9-]+$")
    definition: str = Field(min_length=1, max_length=500)


class Phase3ErrorAttribution(StrictSchema):
    selected_error_code: str | None
    evidence: str = Field(min_length=1, max_length=280)
    confidence: float = Field(ge=0.0, le=1.0)


class Phase3ReviewEvidence(StrictSchema):
    evaluation: EvaluationCategory | None
    independent_outcome: IndependentOutcome
    generic_error_type: ErrorType | None
    selected_error_code: str | None
    first_error_step: str | None
    canvas_submitted: StrictBool
    ocr_clear: StrictBool | None
    review_material_available: StrictBool = False


class CanvasMistakeClassification(StrictSchema):
    status: MistakeStatus
    mistake_step_id: str | None
    target_text: str | None
    target_span: list[int] | None
    replacement_text: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    target_token_ids: list[str] = Field(default_factory=list)
    error_token: str | None = None
    expected_token: str | None = None
    localization_status: LocalizationStatus = "not_applicable"


class CanvasAnnotationIntent(StrictSchema):
    kind: AnnotationIntentKind
    target_step_id: str
    text: str | None
    placement: AnnotationPlacement | None


class CanvasMathReview(StrictSchema):
    error_type: ErrorType | None
    tutor_feedback: str | None
    canvas_feedback: CanvasFeedback
    mistake_classification: CanvasMistakeClassification
    annotation_intents: list[CanvasAnnotationIntent]


class SafetyCheck(StrictSchema):
    passed: StrictBool
    flag_type: str | None
    action_taken: str | None


class GuardrailCheck(StrictSchema):
    passed: StrictBool
    violation_type: str | None
    action_taken: str | None


class StudentModelEvent(StrictSchema):
    event_type: LearningEventType
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    hint_level_used: int = Field(ge=0, le=3)
    independent_success: StrictBool


class TutorResponse(StrictSchema):
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    intent: IntentType
    response_strategy: ResponseStrategy
    tutor_message: str
    tutor_message_voice_optimised: str
    voice_optimised: StrictBool
    hint_level: HintLevel | None
    scaffold_steps_delivered: list[str]
    visual_cue: VisualCue
    canvas_feedback: CanvasFeedback
    mistake_classification: CanvasMistakeClassification | None
    annotation_intents: list[CanvasAnnotationIntent]
    next_phase_recommendation: LearningPhase
    answer_reveal_allowed: StrictBool
    confidence: float = Field(ge=0.0, le=1.0)
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    safety_check: SafetyCheck
    guardrail_check: GuardrailCheck
    student_model_events: list[StudentModelEvent]
    attempt_increment: int = Field(ge=0, le=1)
    recommended_conversation_action: ConversationAction
    question_completed: StrictBool
    answer_value_confirmed: StrictBool = False
    reasoning_complete: StrictBool = False
    guided_student_state: GuidedStudentState | None = None
    selected_error_code: str | None = None
    generated_question_rubric: GeneratedQuestionRubric | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    scaffold_original_answer_correct: StrictBool = False
    independent_outcome: IndependentOutcome | None = None
    independent_success: StrictBool | None = None
    independent_attempt_terminal: StrictBool = False
    first_error_step: str | None = None
    phase3_review_evidence: Phase3ReviewEvidence | None = None


class AuthoredRequiredComponent(StrictSchema):
    component_id: str = Field(min_length=1)
    sequence_no: int = Field(ge=1)
    required: StrictBool
    evaluation_criterion: str = Field(min_length=1)


class RecordedMisconception(StrictSchema):
    error_code: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ActiveScaffoldState(StrictSchema):
    scaffold_id: str = Field(min_length=1)
    current_step_id: str = Field(min_length=1)
    step_number: int = Field(ge=1)
    total_steps: int = Field(ge=1)
    step_text: str = Field(min_length=1)
    step_voice: str | None


class AuthoredAnswerSpec(StrictSchema):
    answer_spec_id: str = Field(min_length=1)
    canonical_answer: str = Field(min_length=1)
    accepted_answers: list[str]
    verification_method: str = Field(min_length=1)
    explanation_required: StrictBool | None
    required_components: list[AuthoredRequiredComponent] = Field(min_length=1)


class ExplainAgainRequest(StrictSchema):
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer_spec: AuthoredAnswerSpec
    active_teaching_objective: ActiveTeachingObjective
    first_unresolved_concept_id: str = Field(min_length=1)
    guided_student_state: GuidedStudentState
    selected_error_code: str | None
    recorded_misconception: RecordedMisconception | None
    recent_conversation: list[ConversationMessage]
    active_support_level: SupportUsed
    highest_support_used: SupportUsed
    visible_visual_cue: VisualCue | None
    active_scaffold: ActiveScaffoldState | None
    answer_reveal_allowed: StrictBool


class OpenAIExplainAgainMessage(StrictSchema):
    tutor_message: str = Field(min_length=1)
    tutor_message_voice_optimised: str = Field(min_length=1)
    answer_reveal_risk: StrictBool
    confidence: float = Field(ge=0.0, le=1.0)


class ExplainAgainResult(StrictSchema):
    interaction_type: Literal["EXPLAIN_AGAIN"]
    tutor_message: str = Field(min_length=1)
    tutor_message_voice_optimised: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    attempt_increment: Literal[0]
    evaluation_reason_code: Literal["EXPLAIN_AGAIN_REEXPRESSION"]
    guided_student_state: GuidedStudentState
    active_teaching_objective: ActiveTeachingObjective
    first_unresolved_concept_id: str = Field(min_length=1)
    selected_error_code: str | None
    support_served_this_turn: None
    active_support_level: SupportUsed
    highest_support_used: SupportUsed
    active_scaffold: ActiveScaffoldState | None
    progression_change_requested: Literal[False]
