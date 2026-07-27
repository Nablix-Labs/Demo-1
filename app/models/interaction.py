from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.adapters import (
    ConversationAction,
    ConversationMessage,
    ExpectedStudentResponse,
    VisualCue,
)
from app.models.fields import (
    BoundedText,
    ConceptId,
    InputSource,
    InteractionMode,
    InteractionType,
    Phase,
    QuestionId,
    SessionId,
    StudentId,
    TurnId,
)
from app.models.session import CanvasState, SessionSummary, VoiceState


class InteractionRequest(BaseModel):
    """Validated student interaction sent during an active tutoring session."""

    session_id: SessionId
    student_id: StudentId
    interaction_type: InteractionType
    input_source: InputSource
    text_input: BoundedText | None = None
    voice_transcript: str | None = None
    transcript_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    turn_id: TurnId | None = None
    previous_tutor_turn_id: TurnId | None = None
    transcript_final: bool | None = None
    canvas_snapshot_id: str | None = None
    current_phase: Phase
    concept_id: ConceptId
    question_id: QuestionId
    hint_count: int
    attempt_count: int | None = Field(default=None, ge=0)
    question_completed: bool | None = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    timestamp: str | None = None

    @model_validator(mode="after")
    def validate_voice_turn(self) -> "InteractionRequest":
        if self.input_source != "VOICE":
            return self
        if self.turn_id is None:
            raise ValueError("turn_id is required for VOICE interactions.")
        if self.transcript_final is not True:
            raise ValueError("transcript_final must be true for VOICE interactions.")
        return self


class InteractionResponse(BaseModel):
    """Unified frontend session view returned after a student interaction."""

    session_id: str
    student_id: str
    status: Literal[
        "DUPLICATE_TURN",
        "CLARIFICATION_REQUIRED",
    ] | None = None
    accepted_turn_id: TurnId | None = None
    tutor_turn_id: TurnId | None = None
    conversation_action: ConversationAction
    expects_student_response: bool
    expected_student_response: ExpectedStudentResponse
    retry_safe: bool | None = None
    expected_previous_tutor_turn_id: TurnId | None = None
    attempt_increment: int = Field(ge=0, le=1)
    phase_changed: bool = False
    previous_phase: Phase | None = None
    phase_transition_message: str | None = None
    phase_transition_voice: str | None = None
    current_phase: Phase
    current_question: str
    question_id: str | None = None
    interaction_mode: InteractionMode
    voice_state: VoiceState
    canvas_state: CanvasState
    ui_state: str
    message: str
    message_voice: str
    show_canvas: bool
    show_hint_button: bool
    show_visual_cue: bool
    visual_cue: VisualCue | None
    show_scaffold_panel: bool
    scaffold_steps: list[str]
    allow_text_input: bool
    allow_voice_input: bool
    hint_count: int
    attempt_count: int
    question_completed: bool
    answer_value_confirmed: bool
    phase_indicator: Phase
    recommended_entry_phase: str | None
    session_summary: SessionSummary | None


class StaleTurnResponse(BaseModel):
    status: Literal["STALE_TURN"]
    accepted_turn_id: None
    expected_previous_tutor_turn_id: TurnId | None
    conversation_action: Literal["WAIT_FOR_STUDENT"]
    attempt_increment: Literal[0]
    retry_safe: Literal[False]
    message: str
