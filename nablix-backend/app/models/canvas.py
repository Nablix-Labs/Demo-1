from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.adapters import TutorResult, VisionOCRResult
from app.models.fields import SessionId, SnapshotDataUrl, StudentId


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
