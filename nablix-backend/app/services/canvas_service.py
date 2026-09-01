import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.ai_engine.classifier import (
    build_openai_ai_engine_client,
    build_support_aware_tutor_message,
)
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.config import get_settings
from app.core.exceptions import DOWNSTREAM_FAILURE, JourneyVersionConflict
from app.core.logger import logger
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
)
from app.models.interaction import InteractionResponse, StaleTurnResponse
from app.services.canvas_annotations import (
    plan_canvas_draw,
    plan_write_request_tutor_actions,
    plan_write_request_tutor_draw,
)
from app.models.session import SessionRecord
from app.models.student_model_session import StudentModelQuestion
from app.services.canvas_evidence import (
    CanvasEvidence,
    canvas_events_are_stale,
    collect_canvas_evidence,
    validate_canvas_payload,
)
from app.services.guided_question_opening import guided_question_opening
from app.services.pdf_assembly import PdfAssemblyError, assemble_pdf
from app.models.work_artifact import WorkArtifactPersistRequest
from app.services.interaction_service import (
    _current_hint_level_from,
    _independent_correct_in_session,
    _is_complete_correct_canvas,
    _initialize_restored_schema_phase,
    _phase_2_prompt_context,
    _schema_visual_cue,
    _schema_question,
    _stale_turn_response,
    _guided_rescue,
    _scaffold_evaluation_context,
    process_answer_with_session_event,
    _response_from,
)
from app.services.session_service import (
    _get_owned_session,
    cache_interaction_response,
    interaction_payload_fingerprint_for,
    last_interaction_response_for,
    record_canvas_attachment,
    reconcile_journey_conflict,
    record_canvas_submission,
)
from app.services.student_model_debug import begin as begin_student_model_debug
from app.services.student_model_debug import payload as student_model_debug_payload


_CANVAS_RELATION_PATTERN = re.compile(
    r"(?:\\+(?:rightarrow|to)|[→⟶⟹⇒])"
)
_UNRELIABLE_EVIDENCE_MESSAGE = "Please write out that step so I can check it."
_MISSING_OPERATION_CANVAS_PATTERN = re.compile(r"^[a-z]\s+\d+$", re.IGNORECASE)


def _canvas_request_fingerprint(request: CanvasSubmitRequest) -> str:
    payload = request.model_dump(mode="json", exclude_none=True)
    payload.pop("canvas_events", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _semantic_canvas_text(ocr: VisionOCRResult) -> str:
    """Translate OCR relation notation into prose the answer evaluator can credit."""

    written_work = "\n".join(ocr.detected_steps) or ocr.raw_ocr_text
    return _CANVAS_RELATION_PATTERN.sub(" means ", written_work)


def _clarification_result(
    ocr: VisionOCRResult,
    rules: ClassifierRulesConfig,
    context: AdapterContext,
) -> TutorResult:
    normalized_ocr_text = re.sub(r"\s+", " ", ocr.raw_ocr_text).strip()
    missing_operation = _MISSING_OPERATION_CANVAS_PATTERN.fullmatch(normalized_ocr_text)
    message = _UNRELIABLE_EVIDENCE_MESSAGE
    message_source = "controller"
    if missing_operation:
        fallback_message = rules.guided_learning.critical_thinking.missing_operation_canvas_prompt
        authored_message = build_support_aware_tutor_message(
            question_id=context.question_id,
            question=context.question or "",
            correct_answer=context.correct_answer or "",
            student_input=ocr.raw_ocr_text,
            evaluation="UNCLEAR",
            error_type="INSUFFICIENT_INFORMATION",
            response_strategy="CLARIFY",
            hint_level=None,
            conversation_history=context.conversation_history,
            support_context={
                "diagnostic_focus": "MISSING_OPERATION",
                "ocr_evidence": normalized_ocr_text,
                "response_constraints": (
                    rules.guided_learning.critical_thinking
                    .missing_operation_canvas_llm_constraints
                ),
            },
            openai_client=build_openai_ai_engine_client(get_settings()),
        )
        message = (
            authored_message.tutor_message
            if authored_message is not None
            else fallback_message
        )
        message_source = "openai" if authored_message is not None else "configured_fallback"
    logger.info(
        "canvas_clarification_diagnostics",
        extra={
            "question_id": context.question_id,
            "diagnostic_focus": "MISSING_OPERATION" if missing_operation else "OCR_UNCLEAR",
            "message_source": message_source,
            "ocr_evidence": normalized_ocr_text,
        },
    )
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
        requires_written_math_evidence=True,
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


async def _store_work_artifact(
    session: SessionRecord,
    schema_question: StudentModelQuestion,
    evidence: CanvasEvidence,
    access_token: str,
) -> str | None:
    """Store this attempt's Phase 3 work as one PDF; return its artifact id.

    Storage failures must never fail the student's submission, so this returns
    None and logs instead of raising. The attempt is still evaluated and routed
    exactly as before; only the Phase 4 replay of this attempt is lost.
    """

    event = session.student_model_event
    if event is None or session.question_id is None:
        return None
    try:
        pdf = assemble_pdf(evidence.page_data_urls)
        stored = await get_adapters().student_model.persist_work_artifact(
            WorkArtifactPersistRequest(
                submission_id=evidence.submission_id,
                student_id=session.student_id,
                topic_id=event.journey_state.topic_id,
                question_id=session.question_id,
                question_usage_id=schema_question.question_usage_id,
                page_count=len(evidence.page_data_urls),
                combined_pdf_base64=base64.b64encode(pdf).decode(),
                per_page_ocr_text=evidence.page_ocr_texts,
                combined_ocr_text=evidence.ocr.raw_ocr_text,
            ),
            access_token,
        )
    except (*DOWNSTREAM_FAILURE, PdfAssemblyError) as error:
        logger.warning(
            "work_artifact_not_stored",
            extra={
                "session_id": session.session_id,
                "question_id": session.question_id,
                "error": str(error),
            },
        )
        return None
    return stored.artifact_id


async def submit_canvas(
    request: CanvasSubmitRequest,
    access_token: str,
) -> InteractionResponse | StaleTurnResponse:
    """Recognize a canvas snapshot, run it through the tutor, and store the result."""

    settings = get_settings()
    # /canvas/submit calls process_answer_with_session_event directly, so it never
    # passes through process_interaction's boundary.
    begin_student_model_debug(settings.debug_json_view)
    # Load the session up front so a stale/unknown session 404s before we pay for OCR.
    session = _get_owned_session(request.session_id, request.student_id)
    if (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and request.submission_role == "STANDALONE_ATTEMPT"
        and request.turn_id is None
    ):
        raise HTTPException(
            status_code=422,
            detail="turn_id is required for Independent Practice Canvas submissions.",
        )
    if request.turn_id is not None:
        previous = last_interaction_response_for(request.session_id, request.turn_id)
        if previous is not None:
            fingerprint = interaction_payload_fingerprint_for(
                request.session_id,
                request.turn_id,
            )
            if fingerprint != _canvas_request_fingerprint(request):
                raise HTTPException(
                    status_code=409,
                    detail="turn_id was already accepted with different Canvas evidence.",
                )
            return previous.model_copy(
                update={
                    "status": "DUPLICATE_TURN",
                    "attempt_increment": 0,
                    "retry_safe": True,
                }
            )
    validate_canvas_payload(request.strokes, request.canvas_events)
    session = await _initialize_restored_schema_phase(
        session,
        get_adapters().student_model,
        access_token,
    )
    if canvas_events_are_stale(request.canvas_events, session.question_id):
        return _stale_turn_response(session)
    schema_question = _schema_question(session)
    turn_session = session
    submission_id = request.turn_id or uuid4().hex
    canvas_evidence = await collect_canvas_evidence(
        request.snapshot_data_url,
        request.strokes,
        submission_id,
        get_adapters().vision,
        request.additional_pages,
    )
    snapshot_reference = canvas_evidence.snapshot_reference
    ocr = canvas_evidence.ocr
    canvas_regions = ocr.detected_regions
    ocr_latency_ms = canvas_evidence.ocr_latency_ms
    # Every Phase 3 submit stores its work, wrong or right: correct attempts are
    # evidence, wrong ones are replayed in Phase 4. A page OCR read nothing on is
    # neither -- the turn is UNCLEAR, so it carries no attempt and no detected
    # errors, and _replay_item could never surface the artifact. Multi-page is
    # covered too: raw_ocr_text is the join of every page (canvas_evidence).
    work_artifact_id: str | None = None
    if (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and request.submission_role == "STANDALONE_ATTEMPT"
        and ocr.raw_ocr_text.strip() != ""
    ):
        work_artifact_id = await _store_work_artifact(
            session,
            schema_question,
            canvas_evidence,
            access_token,
        )

    written_work = _semantic_canvas_text(ocr)
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
        canvas_mathml_blocks=ocr.mathml_blocks,
        spatial_tokens=canvas_evidence.spatial_tokens,
        canvas_events=request.canvas_events,
        conversation_history=recent_history,
        generated_question_rubric=session.generated_question_rubric,
        active_teaching_objective=session.active_teaching_objective,
        guided_teaching_state=session.guided_teaching_state,
        scaffold_evaluation_context=(
            _scaffold_evaluation_context(session) if scaffold_turn else None
        ),
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=_is_complete_correct_canvas(
            ocr,
            session.correct_answer,
        ),
        phase3_submission_confirmed=(
            session.current_phase == "INDEPENDENT_PRACTICE"
            and request.submission_role != "VOICE_ATTACHMENT"
        ),
        phase3_submission_kind=(
            "CANVAS"
            if session.current_phase == "INDEPENDENT_PRACTICE"
            and request.submission_role != "VOICE_ATTACHMENT"
            else None
        ),
        phase3_allowed_error_definitions=schema_question.tutor_view.potential_errors,
    )

    tutor_started = perf_counter()
    if request.submission_role == "VOICE_ATTACHMENT":
        tutor = _attachment_result(ocr)
        student_result = None
        schema_content_response = None
        updated_session = session
    elif ocr.needs_clarification or ocr.confidence < max(
        settings.min_ocr_confidence_threshold,
        rules.guided_learning.minimum_ocr_confidence,
    ):
        tutor = _clarification_result(ocr, rules, context)
        student_result = None
        schema_content_response = None
        updated_session = session
    else:
        try:
            student_result, tutor, schema_content_response, _schema_response, updated_session = (
                await process_answer_with_session_event(
                    context,
                    session,
                    access_token,
                )
            )
        except JourneyVersionConflict as conflict:
            await reconcile_journey_conflict(
                request.session_id, request.student_id, conflict
            )
            raise
        tutor = tutor.model_copy(
            update={"next_phase_recommendation": student_result.recommended_entry_phase}
        )
    tutor_latency_ms = (perf_counter() - tutor_started) * 1000
    phase3_silent = turn_session.current_phase == "INDEPENDENT_PRACTICE"
    canvas_draw = (
        []
        if phase3_silent
        else [
            *plan_canvas_draw(tutor, canvas_regions, canvas_evidence.spatial_tokens),
            *(
                plan_write_request_tutor_draw(request.turn_id or "TURN-0000")
                if tutor.requires_written_math_evidence
                else []
            ),
        ]
    )

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
    question_advanced = (
        updated_session.question_id is not None
        and updated_session.question_id != turn_session.question_id
        and updated_session.current_question is not None
    )
    response_message = tutor.tutor_message
    response_message_voice = tutor.tutor_message_voice
    response_action = tutor.recommended_conversation_action
    if question_advanced and updated_session.current_phase == "GUIDED_PRACTICE":
        response_message = guided_question_opening(
            updated_session.current_question,
            updated_session.question_type,
            "Nice work. Here is the next question.",
        )
        response_message_voice = response_message
        response_action = "ADVANCE_TO_NEXT_QUESTION"
    updated_history: list[ConversationMessage] = [
        *session.conversation_history,
        ConversationMessage(role="user", content=message),
        ConversationMessage(role="assistant", content=response_message),
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
            request.strokes,
            request.canvas_events,
        )
    else:
        updated_session = await record_canvas_submission(
            request.session_id,
            request.student_id,
            updated_session,
            turn_session,
            record,
            updated_history,
            student_result,
            request.strokes,
            request.canvas_events,
            work_artifact_id,
        )
    phase_changed = updated_session.current_phase != turn_session.current_phase
    status_to_return = (
        "processed"
        if request.submission_role == "VOICE_ATTACHMENT"
        else "CLARIFICATION_REQUIRED"
        if tutor.evaluation == "UNCLEAR"
        else "processed"
    )
    visual_cue = (
        tutor.visual_cue
        if tutor.visual_cue.show
        else _schema_visual_cue(updated_session.student_model_event)
    )
    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=submission_id,
        interaction_type="ANSWER_SUBMISSION",
        nudge_id=None,
        session=updated_session,
        message=response_message,
        message_voice=response_message_voice,
        visual_cue=visual_cue,
        scaffold_steps=tutor.scaffold_steps_delivered,
        session_summary=None,
        conversation_action=response_action,
        attempt_increment=tutor.attempt_increment,
        status=status_to_return,
        retry_safe=None,
        previous_phase=turn_session.current_phase if phase_changed else None,
    )
    response.submission_id = submission_id
    response.snapshot_reference = snapshot_reference
    response.tutor = tutor.model_copy(
        update={
            "tutor_message": response_message,
            "tutor_message_voice": response_message_voice,
            "visual_cue": visual_cue or tutor.visual_cue,
        }
    )
    response.next_expected_input = (
        "WRITE" if tutor.requires_written_math_evidence else None
    )
    response.write_instruction = (
        tutor.write_instruction if tutor.requires_written_math_evidence else None
    )
    response.canvas_draw = canvas_draw
    response.tutor_canvas_actions = (
        plan_write_request_tutor_actions(request.turn_id or "TURN-0000", 1)
        if tutor.requires_written_math_evidence
        else tutor.tutor_canvas_actions
    )
    response.localization_status = (
        "grounded" if canvas_evidence.spatial_tokens else "uncertain"
    )
    response.ocr = None if phase3_silent else ocr
    response.latency = latency
    response.guided_rescue = _guided_rescue(schema_content_response)
    response.advance_to_next_question = question_advanced
    if phase3_silent:
        response.phase3_submission_kind = "CANVAS"
        response.tutor = None
        if tutor.evaluation == "UNCLEAR":
            response.message = "Please rewrite your answer clearly on the canvas, then submit it again."
            response.message_voice = ""
            response.phase3_submission_confirmed = True
            response.independent_outcome = "INPUT_UNCLEAR"
            response.independent_success = None
            response.independent_attempt_terminal = False
            response.first_error_step = None
            response.phase3_review_evidence = None
        else:
            response.message = (
                "Answer recorded."
                if tutor.independent_outcome == "INDEPENDENTLY_VERIFIED"
                else "We'll review this one before a fresh independent check."
            )
            response.message_voice = ""
            response.phase3_submission_confirmed = tutor.independent_outcome is not None
            response.independent_outcome = tutor.independent_outcome
            response.independent_success = tutor.independent_success
            response.independent_attempt_terminal = tutor.independent_attempt_terminal
            response.first_error_step = None
            response.phase3_review_evidence = None
    cache_interaction_response(
        request.session_id,
        submission_id,
        response,
        _canvas_request_fingerprint(request),
    )
    # After caching, via model_copy: the cache holds the response by reference, so
    # a duplicate replay must not inherit this turn's exchange.
    debug = student_model_debug_payload()
    if debug is not None:
        response = response.model_copy(update={"debug": debug})
    return response
