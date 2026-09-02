from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.adapters import (
    CanvasFeedback,
    ConversationMessage,
    ExpectedStudentResponse,
    StudentModelResult,
    TutorAction,
    VisualCue,
    VisionOCRResult,
)
from app.models.canvas import CanvasQuestionMemory, CanvasSubmissionRecord
from app.models.phase4_review import Phase4ReviewResponse
from app.models.fields import (
    ConceptId,
    InteractionMode,
    NonEmptyText,
    Phase,
    QuestionId,
    SessionId,
    StudentId,
    TurnId,
)
from app.models.guided_learning import (
    ActiveGuidedRescue,
    ActiveTeachingObjective,
    GuidedTeachingState,
    GeneratedQuestionRubric,
    GuidedStudentState,
    InactivityPolicy,
    TutorCanvasAction,
    inactivity_policy,
)
from app.models.student_model_session import (
    PublicStudentModelEvent,
    QuestionType,
    StudentModelCoreState,
    StudentModelSessionEventResponse,
    StudentModelQuestion,
)
from app.services.phase1_tutor import Phase1TutorMessages


NudgeDeliveryStatus = Literal[
    "GENERATED",
    "PRESENTED",
]


class InactivityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_idle_threshold_ms: int = Field(ge=1)
    cooldown_ms: int = Field(ge=1)
    max_nudges_per_tutor_turn: int = Field(ge=1)
    generated_nudge_rate_limit: int = Field(ge=1)


class NudgeDeliveryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: TurnId
    session_id: SessionId
    source_tutor_turn_id: TurnId
    question_id: QuestionId
    message: str
    message_voice: str
    status: NudgeDeliveryStatus
    created_at: datetime
    presented_at: datetime | None = None
    acknowledged_at: datetime | None = None


class VoiceState(BaseModel):
    """Voice-channel state surfaced to the frontend (mock defaults for now)."""

    stream_active: bool = False
    current_turn: Literal["STUDENT", "TUTOR"] = "STUDENT"
    last_transcript_confidence: float | None = None
    fallback_active: bool = False


class CanvasState(BaseModel):
    """Canvas-channel state surfaced to the frontend (mock defaults for now)."""

    canvas_active: bool = True
    snapshot_id: str | None = None
    ocr_result: VisionOCRResult | None = None


class SessionStartRequest(BaseModel):
    """Validated input required to start a tutoring session."""

    student_id: StudentId
    # Saravanan's Student Model owns topic identity. When topic_code is sent it
    # IS the topic -- no lookup, so a new topic never needs a Nablix deploy.
    # concept_id survives only as the RAG/Qdrant key; older clients that send it
    # alone still resolve through settings.student_model_topic_codes.
    topic_code: ConceptId | None = None
    concept_id: ConceptId | None = None
    interaction_mode: InteractionMode
    initial_phase: Phase | None = None


class SessionEndRequest(BaseModel):
    """Validated request to end an active tutoring session."""

    session_id: SessionId
    student_id: StudentId


class SessionResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    turn_id: TurnId
    # All three below are server-authoritative: the client only honestly knows
    # student_id and turn_id. If sent anyway (an older client), they're used as
    # given; otherwise resume_session fills them from stored session state and
    # policy (see Settings.resume_continuity_threshold_days).
    last_activity_at: datetime | None = None
    continuity_threshold_days: int | None = Field(default=None, ge=1)
    saved_journey: dict[str, object] | None = None


class ReviewCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    turn_id: TurnId


class RescueRenderAckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    action_id: NonEmptyText
    status: Literal["RENDERED"]
    target_object_id: NonEmptyText


class RescueAdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    question_id: QuestionId
    rescue_id: NonEmptyText
    current_step_index: int = Field(ge=1)
    trigger: Literal["UI_NEXT", "UI_NEXT_STEP", "VOICE_NEXT"]


class RescueStepResponse(BaseModel):
    # Both are None once the rescue completes: there is no next step to render.
    action: TutorCanvasAction | None = None
    current_step_index: int | None = Field(default=None, ge=1)
    completed: bool = False

    @model_validator(mode="after")
    def validate_step(self) -> "RescueStepResponse":
        if self.completed != (self.action is None):
            raise ValueError("an unfinished rescue must carry its current action.")
        return self


class DiagnosticAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: QuestionId
    student_response: NonEmptyText


class DiagnosticCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    answers: list[DiagnosticAnswer]


class OrientationPhaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId


class OrientationCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: StudentId
    completed_video_ids: list[NonEmptyText]
    completed_worked_example_ids: list[NonEmptyText]


class QuestionAttemptRecord(BaseModel):
    question_id: QuestionId
    # The question as served, so summaries can show real text, not just ids.
    question_text: str = ""
    phase: Phase
    evaluation: str
    error_type: str | None = None
    input_source: Literal["TEXT", "VOICE", "CANVAS"]
    hint_level_used: int
    attempted_at: datetime
    # Links this attempt to its stored Phase 3 canvas work, so Phase 4 can
    # replay it. None when the work could not be stored, and for every attempt
    # made before work artifacts existed.
    work_artifact_id: str | None = None


class PhaseTransitionRecord(BaseModel):
    previous_phase: Phase
    current_phase: Phase
    entry_reason: str | None
    transitioned_at: datetime


class SessionPerformance(BaseModel):
    total_attempts: int
    correct_attempts: int
    incorrect_attempts: int
    hints_used: int
    hint_levels_used: list[int]
    scaffold_steps_delivered: None
    canvas_submissions: int
    # Phase 3 only, and terminal Phase 3 only. total_attempts counts every
    # phase together, so it cannot answer "how many did they do alone?".
    independent_attempts: int


class SessionSummary(BaseModel):
    session_id: SessionId
    student_id: StudentId
    concept_id: ConceptId
    session_date: datetime
    session_duration_seconds: int
    interaction_mode: InteractionMode
    phase_4_entry_reason: str | None
    phases_completed: list[Phase]
    session_performance: SessionPerformance
    per_question_history: list[QuestionAttemptRecord]
    scaffold_history: None
    canvas_feedback_history: list[CanvasFeedback]
    phase_transitions: list[PhaseTransitionRecord]
    recommended_entry_phase: str | None
    conversation_history: list[ConversationMessage]


class SessionRecord(BaseModel):
    """Current mock session state stored by the in-memory registry."""

    session_id: SessionId
    student_id: StudentId
    concept_id: ConceptId
    started_at: datetime
    current_phase: Phase
    previous_phase: Phase | None = None
    current_question: str | None
    question_type: QuestionType | None = None
    question_id: QuestionId | None
    question_number: int
    # Answer key served with the question (Qdrant payload or demo stub).
    correct_answer: str | None = None
    # Every question id served this session, for knowledge-base exclusion.
    served_question_ids: list[str] = Field(default_factory=list)
    interaction_mode: InteractionMode
    voice_state: VoiceState = Field(default_factory=VoiceState)
    canvas_state: CanvasState = Field(default_factory=CanvasState)
    ui_state: str
    message: str
    diagnostic_transition_message: str | None = None
    diagnostic_transition_messages: list[str] = Field(default_factory=list)
    orientation_messages: Phase1TutorMessages | None = None
    show_canvas: bool = True
    show_hint_button: bool = False
    show_visual_cue: bool = False
    active_visual_cue: VisualCue | None = None
    show_scaffold_panel: bool = False
    scaffold_steps: list[str] = Field(default_factory=list)
    allow_text_input: bool = True
    allow_voice_input: bool = True
    hint_count: int
    attempt_count: int = 0
    wrong_attempt_count: int = 0
    # Terminal Independent Practice results only: the student either answered
    # unaided or needs the rescue. Never raised by unreadable work, a hint, a
    # voice attachment, a stale turn, or a duplicate retry.
    independent_attempt_count: int = 0
    interaction_state_version: int = 0
    nudge_generated_count: int = 0
    nudge_presented_count: int = 0
    last_tutor_response_at: datetime
    last_nudge_generated_at: datetime | None = None
    pending_nudge_id: TurnId | None = None
    pending_nudge_message: str | None = None
    stuck_count: int = 0
    wrong_attempt_count: int = 0
    selected_error_code: str | None = None
    last_tutor_response_at: datetime | None = None
    inactivity_policy: InactivityPolicy | None = None
    # Consecutive REQUEST_EXPLANATION turns on the current question. PARTIAL
    # explanation turns carry attempt_increment=0, so without this nothing
    # counts them and nothing can cap them (31 Jul: 29 consecutive rejections
    # of a reasonable explanation, session unwinnable).
    explanation_request_count: int = 0
    generated_question_rubric: GeneratedQuestionRubric | None = None
    active_teaching_objective: ActiveTeachingObjective | None = None
    guided_teaching_state: GuidedTeachingState | None = None
    guided_student_state: GuidedStudentState | None = None
    selected_error_code: str | None = None
    question_completed: bool = False
    answer_value_confirmed: bool = False
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    last_processed_turn_id: TurnId | None = None
    last_tutor_turn_id: TurnId | None = None
    last_tutor_action: TutorAction = "ASKED_QUESTION"
    expected_student_response: ExpectedStudentResponse = "ANSWER"
    scaffold_id: str | None = None
    current_scaffold_step_id: str | None = None
    scaffold_step_number: int = 0
    scaffold_total_steps: int = 0
    delivered_scaffold_step_ids: list[str] = Field(default_factory=list)
    scaffold_expected_response: str | None = None
    rescue_mode_active: bool = False
    active_guided_rescue: ActiveGuidedRescue | None = None
    # Kept after the rescue is cleared so a client retrying the final
    # acknowledgement gets 200 completed instead of 409.
    last_completed_rescue_action_id: str | None = None
    mastery_check_question_count: int = 0
    # Functional fields the guide omits but the backend needs.
    status: Literal["started", "ended"]
    mode: Literal["inprocess"] = "inprocess"
    canvas_submissions: list[CanvasSubmissionRecord] = Field(default_factory=list)
    canvas_memory_by_question: dict[str, CanvasQuestionMemory] = Field(
        default_factory=dict
    )
    per_question_history: list[QuestionAttemptRecord] = Field(default_factory=list)
    hint_levels_used: list[int] = Field(default_factory=list)
    phase_transitions: list[PhaseTransitionRecord] = Field(default_factory=list)
    recommended_entry_phase: str | None = None
    # Last learner-state snapshot from Saravanan's service, kept so the
    # end-of-session review reflects his data rather than a reconstruction.
    last_student_model: StudentModelResult | None = None
    student_model_event: StudentModelSessionEventResponse | None = None
    # Tutor replay and learning summary, generated once on entering Review.
    # None when the topic has not reached Review, or generation failed.
    phase4_review: Phase4ReviewResponse | None = None
    prerequisite_repair_event: StudentModelSessionEventResponse | None = None
    student_model_state: StudentModelCoreState | None = None
    active_student_model_question: StudentModelQuestion | None = None
    session_summary: SessionSummary | None = None


class SessionResponse(SessionRecord):
    model_config = ConfigDict(from_attributes=True)

    correct_answer: str | None = Field(default=None, exclude=True)
    active_guided_rescue: ActiveGuidedRescue | None = Field(default=None, exclude=True)
    last_completed_rescue_action_id: str | None = Field(default=None, exclude=True)
    scaffold_steps: list[str] = Field(default_factory=list, exclude=True)
    scaffold_expected_response: str | None = Field(default=None, exclude=True)
    student_model_event: PublicStudentModelEvent | None = None
    prerequisite_repair_event: StudentModelSessionEventResponse | None = Field(
        default=None,
        exclude=True,
    )
    active_student_model_question: StudentModelQuestion | None = Field(
        default=None,
        exclude=True,
    )
    generated_question_rubric: GeneratedQuestionRubric | None = Field(
        default=None,
        exclude=True,
    )
    active_teaching_objective: ActiveTeachingObjective | None = Field(
        default=None,
        exclude=True,
    )
    inactivity_policy: InactivityPolicy = Field(default_factory=inactivity_policy)
