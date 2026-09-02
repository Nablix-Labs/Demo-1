from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.adapters import (
    ConversationAction,
    ConversationMessage,
    ExpectedStudentResponse,
    TutorResult,
    VisualCue,
    VisionOCRResult,
)
from app.models.canvas import CanvasDrawPayload, CanvasLatency, CanvasStroke
from app.models.canvas_memory import CanvasEvent, validate_canvas_event_order
from app.models.fields import (
    BoundedText,
    ConceptId,
    InputSource,
    InteractionMode,
    InteractionType,
    Phase,
    QuestionId,
    SessionId,
    SnapshotDataUrl,
    StudentId,
    TurnId,
)
from app.models.question_anchor import QuestionTextAnchor
from app.models.guided_learning import (
    ActiveScaffold,
    GuidedRescue,
    ActiveTeachingObjective,
    GuidedStudentState,
    EvaluationReasonCode,
    TutorCanvasAction,
    PrerequisiteRepair,
    WrongEscalationCode,
)
from app.models.session import (
    CanvasState,
    InactivityPolicy,
    NudgeDeliveryRecord,
    ReviewMaterializationState,
    SessionSummary,
    VoiceState,
)
from app.models.student_model_session import (
    PublicStudentModelEvent,
    QuestionType,
    StudentModelCoreState,
    SupportUsed,
)


class InteractionCanvasState(BaseModel):
    """Frozen canvas evidence paired with a completed voice turn."""

    snapshot_data_url: SnapshotDataUrl
    strokes: list[CanvasStroke] = Field(default_factory=list)
    canvas_events: list[CanvasEvent] = Field(default_factory=list)
    captured_at: datetime

    @model_validator(mode="after")
    def validate_canvas_events(self) -> "InteractionCanvasState":
        validate_canvas_event_order(self.canvas_events)
        return self


class InteractionRequest(BaseModel):
    """Validated student interaction sent during an active tutoring session."""

    session_id: SessionId
    student_id: StudentId
    interaction_type: InteractionType
    input_source: InputSource
    text_input: BoundedText | None = None
    selected_option_id: str | None = None
    voice_transcript: str | None = None
    transcript_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    turn_id: TurnId
    previous_tutor_turn_id: TurnId | None = None
    transcript_final: bool | None = None
    canvas_snapshot_id: str | None = None
    canvas_state: InteractionCanvasState | None = None
    current_phase: Phase
    concept_id: ConceptId
    question_id: QuestionId
    hint_count: int
    attempt_count: int | None = Field(default=None, ge=0)
    question_completed: bool | None = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    idle_duration_ms: int | None = Field(default=None, ge=0)
    nudge_id: TurnId | None = None
    timestamp: str | None = None

    @model_validator(mode="after")
    def validate_turn(self) -> "InteractionRequest":
        if self.input_source == "VOICE" and self.transcript_final is not True:
            raise ValueError("transcript_final must be true for VOICE interactions.")
        system_interactions = {"INACTIVITY_NUDGE", "NUDGE_PRESENTED"}
        if (self.input_source == "SYSTEM") != (
            self.interaction_type in system_interactions
        ):
            raise ValueError(
                "SYSTEM input_source is only valid for inactivity nudge interactions."
            )
        if self.interaction_type == "NUDGE_PRESENTED" and self.nudge_id is None:
            raise ValueError("nudge_id is required for NUDGE_PRESENTED.")
        if self.interaction_type == "OPTION_SELECTED" and self.selected_option_id is None:
            raise ValueError("selected_option_id is required for OPTION_SELECTED.")
        if self.interaction_type == "TEACH_BACK_SUBMISSION" and self.text_input is None:
            raise ValueError("text_input is required for TEACH_BACK_SUBMISSION.")
        if self.interaction_type in system_interactions and self.previous_tutor_turn_id is None:
            raise ValueError(
                "previous_tutor_turn_id is required for inactivity interactions."
            )
        if self.interaction_type == "CLARIFICATION_REQUEST" and self.input_source != "VOICE":
            raise ValueError("CLARIFICATION_REQUEST is only valid for VOICE input.")
        if self.input_source == "CHOICE" and self.selected_option_id is None:
            raise ValueError("selected_option_id is required for CHOICE input.")
        return self


class InteractionResponse(BaseModel):
    """Unified frontend session view returned after a student interaction."""

    session_id: str
    student_id: str
    submission_id: str | None = None
    status: Literal[
        "DUPLICATE_TURN",
        "CLARIFICATION_REQUIRED",
        "NUDGE_SUPPRESSED",
        "processed",
    ] | None = None
    accepted_turn_id: TurnId | None = None
    interaction_state_version: int = Field(default=0, ge=0)
    tutor_turn_id: TurnId | None = None
    conversation_action: ConversationAction
    expects_student_response: bool
    expected_student_response: ExpectedStudentResponse
    next_expected_input: Literal["WRITE"] | None = None
    write_instruction: str | None = Field(default=None, max_length=160)
    retry_safe: bool | None = None
    expected_previous_tutor_turn_id: TurnId | None = None
    attempt_increment: int = Field(ge=0, le=1)
    phase_changed: bool = False
    previous_phase: Phase | None = None
    phase_transition_message: str | None = None
    phase_transition_voice: str | None = None
    current_phase: Phase
    current_question: str | None
    question_type: QuestionType | None = None
    question_id: str | None = None
    interaction_mode: InteractionMode
    voice_state: VoiceState
    canvas_state: CanvasState
    ui_state: str
    message: str
    message_voice: str
    support_message: str | None = None
    show_canvas: bool
    show_hint_button: bool
    show_visual_cue: bool
    visual_cue: VisualCue | None
    show_scaffold_panel: bool
    scaffold_id: str | None = None
    current_scaffold_step_id: str | None = None
    scaffold_step_number: int = 0
    scaffold_step_text: str | None = None
    scaffold_step_voice: str | None = None
    total_scaffold_steps: int = 0
    allow_text_input: bool
    allow_voice_input: bool
    hint_count: int
    attempt_count: int
    question_completed: bool
    answer_value_confirmed: bool
    phase_indicator: Phase
    recommended_entry_phase: str | None
    session_summary: SessionSummary | None
    debug: dict[str, object] | None = None
    student_model_event: PublicStudentModelEvent | None = None
    student_model_state: StudentModelCoreState | None = None
    guided_student_state: GuidedStudentState | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    first_unresolved_concept_id: str | None = None
    selected_error_code: str | None = None
    evaluation_reason_code: EvaluationReasonCode | None = None
    # Deliberately `str`, not RoutingReasonCode: the Student Model owns this
    # vocabulary and adds to it independently (GUIDED_STARTED arrived that way
    # and 500'd completed turns). StudentModelRouting.reason_code is already
    # `str` on the way in, so a closed enum here made the boundary asymmetric.
    # Nothing in the backend or the frontend branches on either field - they are
    # carried through for display and telemetry - so rejecting an unknown code
    # costs a whole tutoring turn and buys nothing. RoutingReasonCode remains
    # the documented set of known values.
    routing_reason_code: str | None = None
    support_reason_code: str | None = None
    support_served_this_turn: SupportUsed | None = None
    active_support_level: SupportUsed = "NONE"
    highest_support_used: SupportUsed = "NONE"
    consecutive_stuck_count: int = Field(default=0, ge=0)
    wrong_attempt_count: int = Field(default=0, ge=0)
    intervention_triggered: bool = False
    active_scaffold: ActiveScaffold | None = None
    guided_rescue: GuidedRescue | None = None
    prerequisite_repair: PrerequisiteRepair | None = None
    inactivity_policy: InactivityPolicy | None = None
    nudge_delivery: NudgeDeliveryRecord | None = None
    canvas_draw: list[CanvasDrawPayload] = Field(default_factory=list)
    tutor_canvas_actions: list[TutorCanvasAction] = Field(default_factory=list)
    # Spans into `current_question` for the frontend to highlight and label.
    question_anchors: list[QuestionTextAnchor] = Field(default_factory=list)
    localization_status: Literal["grounded", "uncertain"] | None = None
    ocr: VisionOCRResult | None = None
    latency: CanvasLatency | None = None
    snapshot_reference: str | None = None
    tutor: TutorResult | None = None
    is_canvas_solution_correct: bool | None = None
    advance_to_next_question: bool = False
    feedback_type: Literal["PRAISE", "HINT", "CORRECTION", "CLARIFICATION"] | None = None
    phase3_submission_confirmed: bool | None = None
    phase3_submission_kind: Literal["CANVAS", "CHOICE"] | None = None
    independent_outcome: Literal[
        "AWAITING_SUBMISSION",
        "INPUT_UNCLEAR",
        "INDEPENDENTLY_VERIFIED",
        "RESCUE_REQUIRED",
    ] | None = None
    independent_success: bool | None = None
    independent_attempt_terminal: bool | None = None
    phase3_locked_question_id: str | None = None
    first_error_step: str | None = None
    phase3_review_evidence: dict[str, object] | None = None
    # Set once the turn has been accepted INTO Review: PENDING means the answer
    # stands and the review screen is still being built, READY that it is there.
    # A null phase4_review with no state here would say the same thing as a
    # failure, which is how "accepted" and "could not be prepared" got confused.
    review_materialization_state: ReviewMaterializationState | None = None


class StaleTurnResponse(BaseModel):
    status: Literal["STALE_TURN"]
    accepted_turn_id: None
    expected_previous_tutor_turn_id: TurnId | None
    conversation_action: Literal["WAIT_FOR_STUDENT"]
    attempt_increment: Literal[0]
    retry_safe: Literal[False]
    message: str
