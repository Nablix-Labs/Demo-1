from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.config import get_settings
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
from app.services.canvas_annotations import assign_step_ids, plan_canvas_draw
from app.services.interaction_service import (
    _current_hint_level_from,
    _independent_correct_in_session,
    _initialize_restored_schema_phase,
    _phase_2_prompt_context,
    _schema_question,
    _scaffold_evaluation_context,
    process_answer_with_session_event,
)
from app.services.session_service import (
    _get_owned_session,
    record_canvas_attachment,
    record_canvas_submission,
)
from app.services.phase_transition import DEFAULT_TRANSITION_MESSAGE, TRANSITION_MESSAGES
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
        attempt_increment=0,
        recommended_conversation_action="REQUEST_CLARIFICATION",
        question_completed=False,
    )


def _attachment_result(ocr: VisionOCRResult) -> TutorResult:
    message = "Canvas work attached. Your voice answer will be graded separately."
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
        attempt_increment=0,
        recommended_conversation_action="WAIT_FOR_STUDENT",
        question_completed=False,
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
    session = await _initialize_restored_schema_phase(
        session,
        get_adapters().student_model,
        access_token,
    )
    schema_question = _schema_question(session)
    previous_session = session

    submission_id = request.turn_id or uuid4().hex
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
    attempt_count: int = (
        session.attempt_count
        if session.answer_value_confirmed
        else session.attempt_count + 1
    )
    recent_history: list[ConversationMessage] = (
        session.conversation_history[-rules.conversation_rules.max_recent_messages :]
        if rules.conversation_rules.max_recent_messages > 0
        else []
    )
    scaffold_turn = session.current_scaffold_step_id is not None

    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        source_turn_id=submission_id,
        question_id=session.question_id,
        message=message,
        question=(
            session.scaffold_steps[0]
            if scaffold_turn and session.scaffold_steps
            else session.current_question
        ),
        question_type=None if scaffold_turn else session.question_type,
        correct_answer=(
            session.scaffold_expected_response
            if scaffold_turn
            else session.correct_answer
        ),
        answer_spec=(
            None if scaffold_turn else schema_question.tutor_view.answer_spec
        ),
        phase_2_prompt_context=_phase_2_prompt_context(session),
        current_phase=session.current_phase,
        input_source="CANVAS",
        transcript_confidence=request.transcript_confidence,
        attempt_count=attempt_count,
        independent_correct_in_session=_independent_correct_in_session(session),
        question_completed=session.question_completed,
        answer_value_confirmed=session.answer_value_confirmed,
        question_number=session.question_number,
        current_hint_level=_current_hint_level_from(session.hint_count),
        concept_id=session.concept_id,
        detected_equation=ocr.detected_equation,
        detected_steps=ocr.detected_steps,
        ocr_confidence=ocr.confidence,
        canvas_regions=canvas_regions,
        conversation_history=recent_history,
        generated_question_rubric=session.generated_question_rubric,
        active_teaching_objective=session.active_teaching_objective,
        scaffold_evaluation_context=(
            _scaffold_evaluation_context(session) if scaffold_turn else None
        ),
    )

    tutor_started = perf_counter()
    if request.submission_role == "VOICE_ATTACHMENT":
        tutor = _attachment_result(ocr)
        student_result = None
        updated_session = session
    elif ocr.needs_clarification or ocr.confidence < settings.min_ocr_confidence_threshold:
        tutor = _clarification_result(ocr)
        student_result = None
        updated_session = session
    else:
        student_result, tutor, _schema_content, _schema_response, updated_session = (
            await process_answer_with_session_event(
                context,
                session,
                access_token,
            )
        )
        tutor = tutor.model_copy(
            update={"next_phase_recommendation": student_result.recommended_entry_phase}
        )
    recommended_entry_phase = (
        student_result.recommended_entry_phase
        if student_result is not None
        else updated_session.recommended_entry_phase
    )
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
        updated_session = await record_canvas_attachment(
            request.session_id,
            request.student_id,
            record,
        )
    else:
        updated_session = await record_canvas_submission(
            request.session_id,
            request.student_id,
            updated_session,
            record,
            updated_history,
            student_result,
        )
    phase_changed = updated_session.current_phase != previous_session.current_phase
    transition_message = (
        TRANSITION_MESSAGES.get(
            (previous_session.current_phase, updated_session.current_phase),
            DEFAULT_TRANSITION_MESSAGE,
        )
        if phase_changed
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
        phase_changed=phase_changed,
        previous_phase=previous_session.current_phase if phase_changed else None,
        current_phase=updated_session.current_phase,
        current_question=str(updated_session.current_question),
        question_id=str(updated_session.question_id),
        ui_state=updated_session.ui_state,
        recommended_entry_phase=recommended_entry_phase,
        phase_transition_message=transition_message,
        phase_transition_voice=transition_message,
    )
