"""Typed contracts exchanged with the tutor, RAG, student-model, and voice adapters.

These DTOs are the seam between the services and whatever sits behind an adapter
(mock today, real HTTP later). Because they are Pydantic models, a malformed
adapter response fails loudly at construction instead of leaking an untyped dict
into the service layer.
"""

from typing import Literal

from pydantic import BaseModel, Field


class AdapterContext(BaseModel):
    """Shared input for the three text adapters (tutor, RAG, student model).

    All three answer the same question — "what is this student doing right now?"
    — so they take one context instead of three near-identical request shapes.
    """

    session_id: str
    student_id: str
    message: str
    question: str | None = None
    correct_answer: str | None = None
    current_phase: str | None = None
    input_source: str | None = None
    transcript_confidence: float | None = None
    attempt_count: int | None = None
    current_hint_level: int | None = None
    concept_id: str | None = None
    canvas_regions: list["OCRTextRegion"] = Field(default_factory=list)


class RetrievedDocument(BaseModel):
    """One piece of learning material returned by the RAG service."""

    title: str
    content: str
    source: str


class RAGResult(BaseModel):
    documents: list[RetrievedDocument]
    retrieval_confidence: float


class StudentModelResult(BaseModel):
    student_state: str
    confidence: float
    mastery_level: str
    recommended_support: str


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
    cue_type: str | None = None
    description: str | None = None


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


class TutorMistakeClassification(BaseModel):
    status: Literal["mistake_found", "no_mistake", "uncertain"]
    mistake_step_id: str | None = None
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
    final_answer: str | None = None
    confidence: float
    needs_clarification: bool = False

    # Additional canvas-understanding fields beyond the task-plan schema
    latex: str | None = None
    detected_shapes: list[DetectedShape] = []
    confidence_source: Literal["mock", "model_estimated", "ocr_native"] = "mock"
    provider: str = "mock"
