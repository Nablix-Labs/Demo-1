"""Typed contracts exchanged with the tutor, RAG, student-model, and voice adapters.

These DTOs are the seam between the services and whatever sits behind an adapter
(mock today, real HTTP later). Because they are Pydantic models, a malformed
adapter response fails loudly at construction instead of leaking an untyped dict
into the service layer.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.canvas_memory import CanvasEvent
from app.models.student_model_session import AnswerSpec, QuestionType
from app.models.guided_learning import (
    ActiveTeachingObjective,
    CanvasPedagogyIntent,
    ConversationMessage,
    GuidedTeachingState,
    GeneratedQuestionRubric,
    GuidedStudentState,
    ScaffoldEvaluationContext,
    TutorCanvasAction,
)

MasteryStatus = Literal[
    "NEW_LEARNER",
    "DEVELOPING",
    "NEARLY_MASTERED",
    "MASTERED",
    "LEARNING_GAP",
    "REVIEW_DUE",
    "RESTART_RECOMMENDED",
]
ContinuityStatus = Literal[
    "on_track",
    "review_due",
    "learning_gap",
    "needs_refresh",
    "restart_recommended",
]
TutorAction = Literal[
    "ASKED_QUESTION",
    "GAVE_HINT",
    "REQUESTED_EXPLANATION",
    "REQUESTED_CLARIFICATION",
    "CONFIRMED_CORRECT_ANSWER",
    "GAVE_INCORRECT_FEEDBACK",
    "ADVANCED_QUESTION",
]
ExpectedStudentResponse = Literal[
    "ANSWER",
    "EXPLANATION",
    "CLARIFICATION",
    "ACKNOWLEDGEMENT_OR_CONTINUE",
    "NONE",
]
ConversationAction = Literal[
    "ASK_QUESTION",
    "GIVE_HINT",
    "ACKNOWLEDGE_ANSWER",
    "REQUEST_EXPLANATION",
    "REQUEST_CLARIFICATION",
    "ADVANCE_TO_NEXT_QUESTION",
    "WAIT_FOR_STUDENT",
]


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    last_tutor_action: TutorAction
    expected_student_response: ExpectedStudentResponse


class Phase2PromptContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target_micro_skill_ids: list[str]
    support_state: dict[str, object]
    potential_errors: list[dict[str, object]]
    support_catalog: dict[str, object]
    current_support: dict[str, object] | None
    current_scaffold_step_number: int
    consecutive_stuck_count: int


class AdapterContext(BaseModel):
    """Shared input for the three text adapters (tutor, RAG, student model).

    All three answer the same question — "what is this student doing right now?"
    — so they take one context instead of three near-identical request shapes.
    """

    session_id: str
    student_id: str
    source_turn_id: str | None = None
    question_id: str | None = None
    question_type: QuestionType | None = None
    message: str
    question: str | None = None
    correct_answer: str | None = None
    answer_spec: AnswerSpec | None = None
    phase_2_prompt_context: Phase2PromptContext | None = None
    current_phase: str | None = None
    input_source: str | None = None
    transcript_confidence: float | None = None
    attempt_count: int | None = None
    independent_correct_in_session: int = 0
    question_completed: bool = False
    answer_value_confirmed: bool = False
    question_number: int | None = None
    current_hint_level: int | None = None
    concept_id: str | None = None
    detected_equation: str | None = None
    detected_steps: list[str] = Field(default_factory=list)
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    canvas_regions: list["OCRTextRegion"] = Field(default_factory=list)
    canvas_mathml_blocks: list[str] = Field(default_factory=list)
    spatial_tokens: list["SpatialMathToken"] = Field(default_factory=list)
    canvas_events: list[CanvasEvent] = Field(default_factory=list)
    has_canvas_evidence: bool = False
    canvas_solution_complete_candidate: bool = False
    conversation_history: list["ConversationMessage"] = Field(default_factory=list)
    conversation_state: ConversationState | None = None
    generated_question_rubric: GeneratedQuestionRubric | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    guided_teaching_state: GuidedTeachingState | None = None
    scaffold_evaluation_context: ScaffoldEvaluationContext | None = None
    phase3_submission_confirmed: bool | None = None
    phase3_submission_kind: Literal["CANVAS", "CHOICE"] | None = None
    phase3_allowed_error_definitions: list[dict[str, object]] = Field(default_factory=list)


class RetrievedDocument(BaseModel):
    """One piece of learning material returned by the RAG service."""

    title: str
    content: str
    source: str


class RAGResult(BaseModel):
    documents: list[RetrievedDocument]
    retrieval_confidence: float


class StudentModelResult(BaseModel):
    """Response contract returned by Saravanan's Student Model service."""

    mastery_status: MasteryStatus
    continuity_status: ContinuityStatus
    recommended_entry_phase: str | None
    hint_dependency_score: float
    intervention_required: bool
    intervention_reason: str | None = None


class TutorEngineRequest(BaseModel):
    context: AdapterContext
    rag: RAGResult
    student: StudentModelResult


class SafetyCheckResult(BaseModel):
    passed: bool
    flag_type: str | None = None
    action_taken: str | None = None
    safe_fallback_message: str | None = None


class StudentModelEvent(BaseModel):
    event_type: str
    evaluation: str
    error_type: str | None = None
    hint_level_used: int
    independent_success: bool


class VisualCue(BaseModel):
    show: bool = False
    cue_id: str | None = None
    cue_type: str | None = None
    description: str | None = None
    asset_url: str | None = None
    actions: list[dict[str, object]] = Field(default_factory=list)


class CanvasStepFeedback(BaseModel):
    step_number: int
    evaluation: str
    error_type: str | None = None
    feedback: str | None = None


class HighlightInstruction(BaseModel):
    step_number: int
    highlight_type: str
    colour: str


class CanvasFeedback(BaseModel):
    has_feedback: bool = False
    step_feedback: list[CanvasStepFeedback] = Field(default_factory=list)
    highlight_instruction: HighlightInstruction | None = None


class SpatialMathToken(BaseModel):
    token_id: str
    step_id: str
    text: str
    latex: str | None = None
    role: Literal[
        "number",
        "identifier",
        "operator",
        "fraction_bar",
        "radical",
        "fence",
        "unknown",
    ] = "unknown"
    semantic_path: str = ""
    stroke_ids: list[str] = Field(default_factory=list)
    bounding_box: dict[str, float] = Field(default_factory=dict)  # x, y, width, height in 0..1
    alignment_confidence: float = 1.0


class TutorMistakeClassification(BaseModel):
    status: Literal["mistake_found", "no_mistake", "uncertain"]
    mistake_step_id: str | None = None
    target_token_ids: list[str] = Field(default_factory=list)
    error_token: str | None = None
    expected_token: str | None = None
    target_text: str | None = None
    target_span: tuple[int, int] | None = None
    replacement_text: str | None = None
    confidence: float


class AnnotationIntent(BaseModel):
    kind: Literal["circle_target", "write_correction", "draw_arrow"]
    target_step_id: str
    text: str | None = None
    placement: Literal["right", "below"] | None = None



class TutorResult(BaseModel):
    evaluation: str
    error_type: str
    intent: str
    response_strategy: str
    tutor_message: str
    tutor_message_voice: str
    voice_optimised: bool
    hint_level: int
    scaffold_steps_delivered: list[str] = Field(default_factory=list)
    visual_cue: VisualCue = Field(default_factory=VisualCue)
    canvas_feedback: CanvasFeedback = Field(default_factory=CanvasFeedback)
    mistake_classification: TutorMistakeClassification | None = None
    annotation_intents: list[AnnotationIntent] = Field(default_factory=list)
    next_phase_recommendation: str | None = None
    answer_reveal_allowed: bool
    confidence: float
    input_source: str
    transcript_confidence: float | None = None
    safety_check: SafetyCheckResult = Field(default_factory=lambda: SafetyCheckResult(passed=True))
    student_model_events: list[StudentModelEvent] = Field(default_factory=list)
    attempt_increment: int = Field(ge=0, le=1)
    recommended_conversation_action: ConversationAction
    question_completed: bool
    answer_value_confirmed: bool = False
    reasoning_complete: bool = False
    guided_student_state: GuidedStudentState | None = None
    selected_error_code: str | None = None
    generated_question_rubric: GeneratedQuestionRubric | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    guided_teaching_state: GuidedTeachingState | None = None
    scaffold_original_answer_correct: bool = False
    independent_outcome: Literal[
        "AWAITING_SUBMISSION",
        "INPUT_UNCLEAR",
        "INDEPENDENTLY_VERIFIED",
        "RESCUE_REQUIRED",
    ] | None = None
    independent_success: bool | None = None
    independent_attempt_terminal: bool = False
    first_error_step: str | None = None
    phase3_review_evidence: dict[str, object] | None = None

    requires_written_math_evidence: bool = False
    canvas_intentions: list[CanvasPedagogyIntent] = Field(default_factory=list)
    tutor_canvas_actions: list[TutorCanvasAction] = Field(default_factory=list)


class VoiceResult(BaseModel):
    transcript: str
    confidence: float
    language: str


class DetectedShape(BaseModel):
    """One geometry figure read off the canvas, separate from written math.

    Only describes what is visible (e.g. "triangle", "right angle marked") and
    does not infer syllabus concepts. `properties` holds visual cues such as
    "parallel", "perpendicular", "right_angle", "equal_sides", or "radius".
    """

    shape_type: str
    label: str | None = None
    description: str
    properties: list[str] = Field(default_factory=list)
    confidence: float


class OCRTextRegion(BaseModel):
    """One OCR text line with its normalized canvas bounding box."""

    step_id: str | None = None
    text: str
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)
    confidence: float
    mathml: str | None = None


class VisionOCRResult(BaseModel):
    """Normalized canvas-understanding output, provider-neutral.

    The first block is the structured OCR schema from the task plan
    (`raw_ocr_text`, `detected_equation`, `detected_steps`, `final_answer`,
    `confidence`, `needs_clarification`). `needs_clarification` is set when the
    text confidence or any shape confidence falls below the configured
    threshold, or when the visible work does not explain how the final answer
    was obtained, so callers never treat an uncertain reading as certain.

    The second block carries extra canvas-understanding fields beyond the task
    plan: LaTeX, drawn geometry (`detected_shapes`), `confidence_source` (OpenAI
    vision estimates confidence rather than reporting a native OCR score), and
    the originating `provider`.
    """

    # Task-plan OCR schema
    raw_ocr_text: str
    detected_equation: str = ""
    detected_steps: list[str] = []
    detected_regions: list[OCRTextRegion] = Field(default_factory=list)
    # Per-symbol boxes when the provider reports them. Distinct from
    # detected_regions, which is one box per written line.
    word_regions: list[OCRTextRegion] = Field(default_factory=list)
    final_answer: str | None = None
    confidence: float
    needs_clarification: bool = False

    # Additional canvas-understanding fields beyond the task-plan schema
    latex: str | None = None
    mathml_blocks: list[str] = Field(default_factory=list)
    detected_shapes: list[DetectedShape] = []
    confidence_source: Literal["mock", "model_estimated", "ocr_native"] = "mock"
    provider: str = "mock"
