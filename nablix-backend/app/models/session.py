from typing import Literal

from pydantic import BaseModel, Field

from app.models.adapters import VisionOCRResult
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


class SessionRecord(BaseModel):
    """Current mock session state stored by the in-memory registry."""

    session_id: SessionId
    student_id: StudentId
    concept_id: ConceptId
    current_phase: Phase
    previous_phase: Phase | None = None
    current_question: str
    question_id: QuestionId
    question_number: int
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
    # Phase-scoped counters reset by 6.7 transitions (see PHASE_COUNTER_RESETS).
    attempt_count: int = 0
    scaffold_step_number: int = 0
    rescue_mode_active: bool = False
    mastery_check_question_count: int = 0
    # Functional fields the guide omits but the backend needs.
    status: Literal["started", "ended"]
    mode: Literal["inprocess"] = "inprocess"
    canvas_submissions: list[CanvasSubmissionRecord] = Field(default_factory=list)
