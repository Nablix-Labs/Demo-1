from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.adapters import CanvasFeedback, ConversationMessage, VisionOCRResult
from app.models.canvas import CanvasSubmissionRecord
from app.models.fields import (
    ConceptId,
    InteractionMode,
    Phase,
    QuestionId,
    SessionId,
    StudentId,
)


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
    concept_id: ConceptId
    interaction_mode: InteractionMode
    initial_phase: Phase | None = None


class SessionEndRequest(BaseModel):
    """Validated request to end an active tutoring session."""

    session_id: SessionId
    student_id: StudentId


class QuestionAttemptRecord(BaseModel):
    question_id: QuestionId
    # The question as served, so summaries can show real text, not just ids.
    question_text: str = ""
    phase: Phase
    evaluation: str
    input_source: Literal["TEXT", "VOICE", "CANVAS"]
    hint_level_used: int
    attempted_at: datetime


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
    current_question: str
    question_id: QuestionId
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
    show_canvas: bool = True
    show_hint_button: bool = False
    show_visual_cue: bool = False
    show_scaffold_panel: bool = False
    scaffold_steps: list[str] = Field(default_factory=list)
    allow_text_input: bool = True
    allow_voice_input: bool = True
    hint_count: int
    attempt_count: int = 0
    question_completed: bool = False
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    scaffold_step_number: int = 0
    rescue_mode_active: bool = False
    mastery_check_question_count: int = 0
    # Functional fields the guide omits but the backend needs.
    status: Literal["started", "ended"]
    mode: Literal["inprocess"] = "inprocess"
    canvas_submissions: list[CanvasSubmissionRecord] = Field(default_factory=list)
    per_question_history: list[QuestionAttemptRecord] = Field(default_factory=list)
    hint_levels_used: list[int] = Field(default_factory=list)
    phase_transitions: list[PhaseTransitionRecord] = Field(default_factory=list)
    recommended_entry_phase: str | None = None
    session_summary: SessionSummary | None = None
