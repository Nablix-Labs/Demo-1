from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.adapters import TutorResult, VisionOCRResult
from app.models.fields import SessionId, SnapshotDataUrl, StudentId

TutorElementKind = Literal[
    "text", "math", "line", "arrow", "rect", "ellipse", "freehand", "highlight"
]

# Required fields per kind (§3.3 of the tutor-writing contract). "math" also needs
# tex-or-text, checked separately below.
_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "text": ("x", "y", "text"),
    "math": ("x", "y"),
    "line": ("from_", "to"),
    "arrow": ("from_", "to"),
    "rect": ("x", "y", "w", "h"),
    "ellipse": ("x", "y", "w", "h"),
    "freehand": ("points",),
    "highlight": ("points",),
}


class TutorElement(BaseModel):
    """One resolution-independent tutor mark. All geometry is normalised 0..1.

    JSON is emitted by alias so it matches the frontend contract exactly:
    `from`, `strokeWidth` (camelCase). Coords out of [0,1] or missing per-kind
    fields are rejected, not repaired.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    kind: TutorElementKind
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    from_: list[float] | None = Field(default=None, alias="from")
    to: list[float] | None = None
    points: list[float] | None = None
    text: str | None = None
    tex: str | None = None
    color: str | None = None
    stroke_width: float | None = Field(default=None, alias="strokeWidth")
    size: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> "TutorElement":
        def unit(v: float | None) -> bool:
            return v is None or 0.0 <= v <= 1.0

        if not all(unit(v) for v in (self.x, self.y, self.w, self.h)):
            raise ValueError("x/y/w/h must be within [0,1]")
        for pair in (self.from_, self.to):
            if pair is not None and (len(pair) != 2 or not all(0.0 <= c <= 1.0 for c in pair)):
                raise ValueError("from/to must be a normalised [x,y] pair within [0,1]")
        if self.points is not None and (
            len(self.points) < 4
            or len(self.points) % 2 != 0
            or not all(0.0 <= c <= 1.0 for c in self.points)
        ):
            raise ValueError("points must be even-length normalised x,y pairs within [0,1]")

        for field in _REQUIRED_FIELDS[self.kind]:
            if getattr(self, field) is None:
                raise ValueError(f"kind '{self.kind}' requires '{field}'")
        if self.kind == "math" and not (self.tex or self.text):
            raise ValueError("kind 'math' requires 'tex' or 'text'")
        return self


class CanvasDrawPayload(BaseModel):
    """Envelope the frontend consumes as a `canvas_draw` message (§3.1)."""

    model_config = ConfigDict(populate_by_name=True)

    author: Literal["tutor"] = "tutor"
    action_id: str | None = Field(default=None, alias="actionId")
    mode: Literal["append", "replace"] = "append"
    elements: list[TutorElement] = Field(default_factory=list)


class CanvasSubmitRequest(BaseModel):
    """Validated request to submit a canvas artifact for later analysis."""

    session_id: SessionId
    student_id: StudentId
    snapshot_data_url: SnapshotDataUrl
    # Optional spoken transcript to grade alongside the canvas (VAD turn). Omitted by
    # the Check button, which stays canvas-only.
    transcript: str | None = None
    transcript_confidence: float | None = None


class CanvasLatency(BaseModel):
    """Per-stage timing for one canvas submission, in milliseconds."""

    ocr_latency_ms: float
    tutor_latency_ms: float
    total_latency_ms: float


class CanvasSubmissionRecord(BaseModel):
    submission_id: str
    snapshot_reference: str
    ocr: VisionOCRResult
    tutor: TutorResult
    latency: CanvasLatency
    submitted_at: datetime


class CanvasSubmitResponse(BaseModel):
    """Processed canvas submission with its OCR result and tutor feedback."""

    session_id: str
    student_id: str
    status: Literal["processed"]
    submission_id: str
    snapshot_reference: str
    ocr: VisionOCRResult
    tutor: TutorResult
    latency: CanvasLatency
