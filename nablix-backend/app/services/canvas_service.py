from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.core.config import get_settings
from app.models.adapters import AdapterContext, VisionOCRResult
from app.models.canvas import (
    CanvasLatency,
    CanvasSubmissionRecord,
    CanvasSubmitRequest,
    CanvasSubmitResponse,
)
from app.services.interaction_service import run_tutor_pipeline
from app.services.session_service import record_canvas_submission
from app.services.snapshot_store import build_reference, store_snapshot


def _tutor_message_for(ocr: VisionOCRResult) -> str:
    """Build the message handed to the tutor pipeline from the canvas result.

    Combines written math and any detected geometry into one structured
    message. When recognition is unsure (text or a shape below threshold), a
    caution is prefixed so the tutor confirms with the student instead of
    grading possibly-misread canvas content.
    """

    written_math = "\n".join(ocr.detected_steps) or ocr.raw_ocr_text
    sections: list[str] = []
    if written_math:
        sections.append(f"Written math:\n{written_math}")
    if ocr.final_answer:
        sections.append(f"Final answer: {ocr.final_answer}")
    if ocr.detected_shapes:
        shape_lines = [
            f"- {shape.shape_type}, {shape.label or 'unlabeled'}, "
            f"confidence {shape.confidence:.2f}"
            for shape in ocr.detected_shapes
        ]
        sections.append("Detected shapes:\n" + "\n".join(shape_lines))

    body = "\n\n".join(sections) or "(no recognizable canvas content)"
    if ocr.needs_clarification:
        return (
            "Some canvas recognition is uncertain. Ask the student to confirm "
            "before grading.\n\n" + body
        )
    return body


async def submit_canvas(request: CanvasSubmitRequest) -> CanvasSubmitResponse:
    """Recognize a canvas snapshot, run it through the tutor, and store the result."""

    settings = get_settings()
    if len(request.snapshot_data_url) > settings.max_snapshot_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Canvas snapshot exceeds the {settings.max_snapshot_bytes} byte limit.",
        )

    submission_id = uuid4().hex
    snapshot_reference = build_reference(submission_id)
    store_snapshot(snapshot_reference, request.snapshot_data_url)

    ocr_started = perf_counter()
    ocr: VisionOCRResult = await get_adapters().vision.recognize(request.snapshot_data_url)
    ocr_latency_ms = (perf_counter() - ocr_started) * 1000

    tutor_started = perf_counter()
    _, _, tutor = await run_tutor_pipeline(
        AdapterContext(
            session_id=request.session_id,
            student_id=request.student_id,
            message=_tutor_message_for(ocr),
        )
    )
    tutor_latency_ms = (perf_counter() - tutor_started) * 1000

    latency = CanvasLatency(
        ocr_latency_ms=ocr_latency_ms,
        tutor_latency_ms=tutor_latency_ms,
        total_latency_ms=ocr_latency_ms + tutor_latency_ms,
    )
    record: CanvasSubmissionRecord = CanvasSubmissionRecord(
        submission_id=submission_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        tutor=tutor,
        latency=latency,
        submitted_at=datetime.now(timezone.utc),
    )
    await record_canvas_submission(request.session_id, request.student_id, record)

    return CanvasSubmitResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        status="processed",
        submission_id=record.submission_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        tutor=tutor,
        latency=latency,
    )
