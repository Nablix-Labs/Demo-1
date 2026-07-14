from pydantic import BaseModel

from app.models.adapters import VisualCue
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
)
from app.models.session import CanvasState, VoiceState


class InteractionRequest(BaseModel):
    """Validated student interaction sent during an active tutoring session."""

    session_id: SessionId
    student_id: StudentId
    interaction_type: InteractionType
    input_source: InputSource
    text_input: BoundedText | None = None
    voice_transcript: str | None = None
    transcript_confidence: float | None = None
    canvas_snapshot_id: str | None = None
    current_phase: Phase
    concept_id: ConceptId
    question_id: QuestionId
    hint_count: int
    timestamp: str | None = None


class InteractionResponse(BaseModel):
    """Unified frontend session view returned after a student interaction."""

    session_id: str
    student_id: str
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
    attempt_count: int = 0
    phase_indicator: Phase
    session_summary: str | None
