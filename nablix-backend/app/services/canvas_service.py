from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.core.config import get_settings
from app.models.adapters import (
    AdapterContext,
    SafetyCheckResult,
    TutorResult,
    VisionOCRResult,
)
from app.models.canvas import (
    CanvasLatency,
    CanvasSubmissionRecord,
    CanvasSubmitRequest,
    CanvasSubmitResponse,
)
from app.services.canvas_annotations import assign_step_ids, plan_canvas_draw
from app.services.interaction_service import (
    _current_hint_level_from,
    run_tutor_pipeline,
)
from app.services.session_service import (
    correct_answer_for,
    _get_owned_session,
    record_canvas_submission,
)
from app.services.snapshot_store import build_reference, store_snapshot


def _clarification_result(ocr: VisionOCRResult) -> TutorResult:
    message = "I could not read that work clearly. Please rewrite it and submit again."
    return TutorResult(
        evaluation="UNCLEAR",
        error_type="INSUFFICIENT_INFORMATION",
        intent="SUBMITTING_ANSWER",
        response_strategy="CLARIFY",
        tutor_message=message,
        tutor_message_voice=message,
        voice_optimised=True,
        hint_level=0,
        answer_reveal_allowed=False,
        confidence=ocr.confidence,
        input_source="CANVAS",
        safety_check=SafetyCheckResult(passed=True),
    )


async def submit_canvas(request: CanvasSubmitRequest) -> CanvasSubmitResponse:
    """Recognize a canvas snapshot, run it through the tutor, and store the result."""

    settings = get_settings()
    if len(request.snapshot_data_url) > settings.max_snapshot_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Canvas snapshot exceeds the {settings.max_snapshot_bytes} byte limit.",
        )

    # Load the session up front so a stale/unknown session 404s before we pay for OCR.
    session = _get_owned_session(request.session_id, request.student_id)

    submission_id = uuid4().hex
    snapshot_reference = build_reference(submission_id)
    store_snapshot(snapshot_reference, request.snapshot_data_url)

    ocr_started = perf_counter()
    ocr: VisionOCRResult = await get_adapters().vision.recognize(request.snapshot_data_url)
    canvas_regions = assign_step_ids(ocr.detected_regions)
    ocr = ocr.model_copy(update={"detected_regions": canvas_regions})
    ocr_latency_ms = (perf_counter() - ocr_started) * 1000

    written_work = "\n".join(ocr.detected_steps) or ocr.raw_ocr_text
    message = "\n".join(part for part in [written_work, request.transcript] if part)
    attempt_count = session.attempt_count + 1
    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        message=message,
        question=session.current_question,
        correct_answer=correct_answer_for(session.question_id),
        current_phase=session.current_phase,
        input_source="CANVAS",
        transcript_confidence=request.transcript_confidence,
        attempt_count=attempt_count,
        current_hint_level=_current_hint_level_from(session.hint_count),
        concept_id=session.concept_id,
        detected_equation=ocr.detected_equation,
        detected_steps=ocr.detected_steps,
        ocr_confidence=ocr.confidence,
        canvas_regions=canvas_regions,
    )

    tutor_started = perf_counter()
    reviewed_attempt_count = session.attempt_count
    if ocr.needs_clarification or ocr.confidence < settings.min_ocr_confidence_threshold:
        tutor = _clarification_result(ocr)
    else:
        _, _, tutor = await run_tutor_pipeline(context)
        adapters = get_adapters()
        for event in tutor.student_model_events:
            await adapters.student_model.update_from_event(event)
        reviewed_attempt_count = attempt_count
    tutor_latency_ms = (perf_counter() - tutor_started) * 1000
    canvas_draw = plan_canvas_draw(tutor, canvas_regions)

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
    await record_canvas_submission(
        request.session_id,
        request.student_id,
        record,
        reviewed_attempt_count,
    )

    return CanvasSubmitResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        status="processed",
        submission_id=record.submission_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        tutor=tutor,
        latency=latency,
        canvas_draw=canvas_draw,
    )
