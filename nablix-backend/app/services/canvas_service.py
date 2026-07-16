from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.config import get_settings
from app.core.exceptions import QuestionFetchError
from app.models.adapters import (
    AdapterContext,
    ConversationMessage,
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
from app.models.fields import Phase
from app.models.session import PhaseTransitionRecord
from app.services.canvas_annotations import assign_step_ids, plan_canvas_draw
from app.services.interaction_service import (
    _current_hint_level_from,
    _independent_correct_in_session,
    run_tutor_pipeline,
)
from app.services.session_service import (
    _get_owned_session,
    get_next_question,
    record_canvas_attachment,
    record_canvas_submission,
    update_interaction_state,
)
from app.services.phase_transition import (
    DEFAULT_TRANSITION_MESSAGE,
    PHASE_COUNTER_RESETS,
    TRANSITION_MESSAGES,
    resolve_transition,
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


async def submit_canvas(
    request: CanvasSubmitRequest,
    access_token: str,
) -> CanvasSubmitResponse:
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
    rules: ClassifierRulesConfig = load_classifier_rules()
    attempt_count: int = session.attempt_count + 1
    recent_history: list[ConversationMessage] = (
        session.conversation_history[-rules.conversation_rules.max_recent_messages :]
        if rules.conversation_rules.max_recent_messages > 0
        else []
    )

    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        message=message,
        question=session.current_question,
        correct_answer=session.correct_answer,
        current_phase=session.current_phase,
        input_source="CANVAS",
        transcript_confidence=request.transcript_confidence,
        attempt_count=attempt_count,
        independent_correct_in_session=_independent_correct_in_session(session),
        question_completed=session.question_completed,
        question_number=session.question_number,
        current_hint_level=_current_hint_level_from(session.hint_count),
        concept_id=session.concept_id,
        detected_equation=ocr.detected_equation,
        detected_steps=ocr.detected_steps,
        ocr_confidence=ocr.confidence,
        canvas_regions=canvas_regions,
        conversation_history=recent_history,
    )

    tutor_started = perf_counter()
    reviewed_attempt_count = session.attempt_count
    recommended_entry_phase: str | None = session.recommended_entry_phase
    student_result = None
    new_phase: Phase | None = None
    transition_updates: dict[str, object] = {}
    if ocr.needs_clarification or ocr.confidence < settings.min_ocr_confidence_threshold:
        tutor = _clarification_result(ocr)
    else:
        _, student, tutor = await run_tutor_pipeline(context)
        if request.submission_role == "STANDALONE_ATTEMPT":
            adapters = get_adapters()
            for event in tutor.student_model_events:
                student = await adapters.student_model.update_from_event(
                    event,
                    context,
                    access_token,
                )
            recommended = student.recommended_entry_phase
            new_phase = resolve_transition(session.current_phase, recommended)
            if new_phase is not None:
                fetched = await get_next_question(
                    session.concept_id,
                    new_phase,
                    session.served_question_ids,
                )
                if fetched is None:
                    raise QuestionFetchError(session.concept_id, new_phase)
                question_text, correct_answer, question_id = fetched
                transition_updates = {
                    "previous_phase": session.current_phase,
                    "current_question": question_text,
                    "question_id": question_id,
                    "correct_answer": correct_answer,
                    "served_question_ids": [*session.served_question_ids, question_id],
                    "question_number": session.question_number + 1,
                    "attempt_count": 0,
                    "question_completed": False,
                    "phase_transitions": [
                        *session.phase_transitions,
                        PhaseTransitionRecord(
                            previous_phase=session.current_phase,
                            current_phase=new_phase,
                            entry_reason="STUDENT_MODEL_RECOMMENDATION",
                            transitioned_at=datetime.now(timezone.utc),
                        ),
                    ],
                    **PHASE_COUNTER_RESETS.get(new_phase, {}),
                }
        authoritative_recommendation = student.recommended_entry_phase
        recommended_entry_phase = authoritative_recommendation
        student_result = student
        tutor = tutor.model_copy(
            update={"next_phase_recommendation": authoritative_recommendation}
        )
        if request.submission_role == "STANDALONE_ATTEMPT":
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
    updated_history: list[ConversationMessage] = [
        *session.conversation_history,
        ConversationMessage(role="user", content=message),
        ConversationMessage(role="assistant", content=tutor.tutor_message),
    ]
    if rules.conversation_rules.max_recent_messages == 0:
        updated_history = []
    else:
        updated_history = updated_history[-rules.conversation_rules.max_recent_messages :]
    if request.submission_role == "VOICE_ATTACHMENT":
        await record_canvas_attachment(
            request.session_id,
            request.student_id,
            record,
        )
    else:
        await record_canvas_submission(
            request.session_id,
            request.student_id,
            record,
            reviewed_attempt_count,
            session.question_completed or tutor.evaluation == "CORRECT",
            updated_history,
            recommended_entry_phase,
            student_result,
        )
        if new_phase is not None:
            _apply_canvas_transition(
                request,
                new_phase,
                transition_updates,
                ocr,
                tutor,
            )

    transition_message = (
        TRANSITION_MESSAGES.get(
            (session.current_phase, new_phase), DEFAULT_TRANSITION_MESSAGE
        )
        if new_phase is not None
        else None
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
        phase_changed=new_phase is not None,
        previous_phase=session.current_phase if new_phase is not None else None,
        current_phase=new_phase or session.current_phase,
        current_question=str(
            transition_updates.get("current_question", session.current_question)
        ),
        question_id=str(transition_updates.get("question_id", session.question_id)),
        ui_state=new_phase or session.ui_state,
        recommended_entry_phase=recommended_entry_phase,
        phase_transition_message=transition_message,
        phase_transition_voice=transition_message,
    )


def _apply_canvas_transition(
    request: CanvasSubmitRequest,
    new_phase: Phase,
    transition_updates: dict[str, object],
    ocr: VisionOCRResult,
    tutor: TutorResult,
) -> None:
    """Apply an authoritative phase recommendation for a standalone attempt."""

    update_interaction_state(
        request.session_id,
        request.student_id,
        new_phase,
        0,
        new_phase,
        request.transcript_confidence,
        None,
        ocr,
        tutor.visual_cue.show,
        len(tutor.scaffold_steps_delivered) > 0,
        tutor.scaffold_steps_delivered,
        transition_updates=transition_updates,
    )
