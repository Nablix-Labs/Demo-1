import asyncio
from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from fastapi import HTTPException
from typing_extensions import NotRequired

from app.adapters.provider import get_adapters
from app.core.config import get_settings
from app.core.logger import logger
from app.models.adapters import ConversationMessage, StudentModelResult, VisionOCRResult
from app.models.canvas import CanvasSubmissionRecord
from app.models.fields import Phase
from app.models.interaction import InteractionResponse
from app.models.session import (
    CanvasState,
    DiagnosticCompleteRequest,
    InactivityPolicy,
    NudgeDeliveryRecord,
    NudgeDeliveryStatus,
    OrientationCompletionRequest,
    OrientationPhaseRequest,
    PhaseTransitionRecord,
    QuestionAttemptRecord,
    SessionEndRequest,
    SessionPerformance,
    SessionRecord,
    SessionStartRequest,
    SessionSummary,
    VoiceState,
)
from app.models.student_model_session import (
    DiagnosticResult,
    DiagnosticCompletedEvent,
    JourneyPhaseState,
    MicroSkillResult,
    OrientationCompletedEvent,
    QuestionType,
    SessionOpenedEvent,
    StudentModelPhasePayload,
    StudentModelPhase,
    StudentModelQuestion,
    StudentModelSessionEventResponse,
    WorkedExampleRequestedEvent,
)
from app.services.phase_transition import (
    TRANSITION_MESSAGES,
    UI_STATE_FLAGS,
    resolve_transition,
)
from app.services.phase0_tutor import load_phase0_tutor_config
from app.services.phase1_tutor import load_phase1_tutor_messages
from app.services.student_model_session import (
    PHASE_FROM_STUDENT_MODEL,
    project_student_model_state,
    schema_hint,
    schema_support_steps,
    schema_visual_cue,
)


_sessions: dict[str, SessionRecord] = {}
_interaction_locks: dict[str, asyncio.Lock] = {}
_last_interaction_responses: dict[tuple[str, str], InteractionResponse] = {}
_nudge_deliveries: dict[tuple[str, str], NudgeDeliveryRecord] = {}

_NUDGE_STATUS_TRANSITIONS: dict[NudgeDeliveryStatus, set[NudgeDeliveryStatus]] = {
    "GENERATED": {"PRESENTED"},
    "PRESENTED": set(),
}


class QuestionUpdates(TypedDict):
    current_question: str | None
    question_type: QuestionType | None
    question_id: str | None
    question_number: NotRequired[int]
    correct_answer: str | None
    served_question_ids: NotRequired[list[str]]


def _build_session_id() -> str:
    return f"SESSION{uuid4().hex}"


def _student_model_request_id(
    session_id: str,
    source_turn_id: str,
    event_type: str,
) -> str:
    return f"{session_id}:{source_turn_id}:{event_type}"


def _session_not_found(session_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"Session with ID {session_id} was not found.",
    )


def interaction_lock_for(session_id: str) -> asyncio.Lock:
    """Return the process-local lock that serializes one session's turns."""

    lock: asyncio.Lock | None = _interaction_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _interaction_locks[session_id] = lock
    return lock


def last_interaction_response_for(
    session_id: str,
    turn_id: str,
) -> InteractionResponse | None:
    return _last_interaction_responses.get((session_id, turn_id))


def cache_interaction_response(
    session_id: str,
    turn_id: str,
    response: InteractionResponse,
) -> None:
    _last_interaction_responses[(session_id, turn_id)] = response


def inactivity_policy() -> InactivityPolicy:
    settings = get_settings()
    return InactivityPolicy(
        initial_idle_threshold_ms=settings.inactivity_initial_idle_threshold_ms,
        cooldown_ms=settings.inactivity_cooldown_ms,
        max_nudges_per_tutor_turn=settings.inactivity_max_nudges_per_tutor_turn,
        generated_nudge_rate_limit=settings.inactivity_generated_nudge_rate_limit,
    )


def nudge_delivery_for(
    session_id: str,
    interaction_id: str,
) -> NudgeDeliveryRecord | None:
    return _nudge_deliveries.get((session_id, interaction_id))


def nudge_deliveries_for_tutor_turn(
    session_id: str,
    source_tutor_turn_id: str,
) -> list[NudgeDeliveryRecord]:
    return [
        record
        for (stored_session_id, _), record in _nudge_deliveries.items()
        if stored_session_id == session_id
        and record.source_tutor_turn_id == source_tutor_turn_id
    ]


def clear_nudge_deliveries_for_session(session_id: str) -> None:
    keys = [key for key in _nudge_deliveries if key[0] == session_id]
    for key in keys:
        del _nudge_deliveries[key]


def store_nudge_delivery(record: NudgeDeliveryRecord) -> NudgeDeliveryRecord:
    key = (record.session_id, record.interaction_id)
    existing = _nudge_deliveries.get(key)
    if existing is not None:
        return existing
    _nudge_deliveries[key] = record
    return record


def update_nudge_delivery_status(
    session_id: str,
    interaction_id: str,
    status: NudgeDeliveryStatus,
    presented_at: datetime | None,
    acknowledged_at: datetime | None,
) -> NudgeDeliveryRecord:
    key = (session_id, interaction_id)
    record = _nudge_deliveries.get(key)
    if record is None:
        raise KeyError(
            f"Nudge delivery not found for session_id={session_id} "
            f"interaction_id={interaction_id}."
        )
    if status not in _NUDGE_STATUS_TRANSITIONS[record.status]:
        raise ValueError(
            f"Invalid nudge delivery transition {record.status}->{status} for "
            f"session_id={session_id} interaction_id={interaction_id}."
        )
    if status == "PRESENTED" and (presented_at is None or acknowledged_at is None):
        raise ValueError(
            "presented_at and acknowledged_at are required for an acknowledged nudge."
        )
    updated = record.model_copy(
        update={
            "status": status,
            "presented_at": presented_at,
            "acknowledged_at": acknowledged_at,
        }
    )
    _nudge_deliveries[key] = updated
    return updated


_SIDE_CHANNEL_UPDATE_FIELDS = {
    "conversation_history",
    "last_processed_turn_id",
    "last_tutor_turn_id",
    "last_tutor_response_at",
    "nudge_generated_count",
    "nudge_presented_count",
}


def update_side_channel_state(
    session: SessionRecord,
    updates: dict[str, object],
) -> SessionRecord:
    unexpected = set(updates) - _SIDE_CHANNEL_UPDATE_FIELDS
    if unexpected:
        raise ValueError(
            f"Side-channel update attempted protected fields: {sorted(unexpected)}."
        )
    updated = session.model_copy(update=updates)
    _sessions[session.session_id] = updated
    return updated


# Retained only for legacy session-review fixtures; active sessions use the
# question and answer specification returned by Student Model Schema 3.0.
_DEMO_QUESTIONS: dict[str, tuple[str, str, int]] = {
    "ALG_EQ_DIAG_001": ("Solve for x: x + 4 = 9", "x = 5", 1),
    "ALG_EQ_CO_001": ("Solve for x: x - 3 = 7", "x = 10", 1),
    "ALG_EQ_GP_001": ("Solve for x: x + 6 = 10", "x = 4", 1),
    "ALG_EQ_IP_001": ("Solve for x: 3x + 2 = 11", "x = 3", 1),
    "ALG_EQ_REV_001": ("Solve for x: x / 2 = 8", "x = 16", 1),
}

def correct_answer_for(question_id: str) -> str | None:
    """Return the expected answer for a question_id, or None if unknown."""

    entry = _DEMO_QUESTIONS.get(question_id)
    return entry[1] if entry else None


def _diagnostic_start_message() -> str:
    return load_phase0_tutor_config().intro_message


def _get_owned_session(session_id: str, student_id: str) -> SessionRecord:
    """Return the session owned by the student or raise a standard 404."""

    return _get_owned_session_for_turn(
        session_id,
        student_id,
        "GUIDED_PRACTICE",
        0,
    )


def _get_owned_session_for_turn(
    session_id: str,
    student_id: str,
    current_phase: Phase,
    hint_count: int,
) -> SessionRecord:
    """Return an in-process Schema 3.0 session for the current turn."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None or session.student_id != student_id:
        raise _session_not_found(session_id)
    if session.student_model_event is None:
        raise HTTPException(
            status_code=409,
            detail="Schema 3.0 session state is required.",
        )
    return session


async def start_session(
    request: SessionStartRequest,
    access_token: str,
) -> SessionRecord:
    """Open the authoritative Schema 3.0 journey."""

    if request.initial_phase is not None:
        raise HTTPException(
            status_code=409,
            detail="Legacy initial_phase sessions are not supported; use Schema 3.0.",
        )

    settings = get_settings()
    topic_id = settings.student_model_topic_codes.get(request.concept_id)
    if topic_id is None:
        raise HTTPException(
            status_code=422,
            detail=f"No Student Model topic code is configured for {request.concept_id}.",
        )

    session_id = _build_session_id()
    started_at = datetime.now(timezone.utc)
    timestamp = started_at.isoformat().replace("+00:00", "Z")
    session_event = SessionOpenedEvent(
        request_id=_student_model_request_id(
            session_id,
            session_id,
            "SESSION_OPENED",
        ),
        event_type="SESSION_OPENED",
        topic_id=topic_id,
        student_id=request.student_id,
        timestamp=timestamp,
    )
    event = await get_adapters().student_model.send_session_event(
        session_event,
        access_token,
    )
    payload = _validate_session_opened_payload(event)
    phase = PHASE_FROM_STUDENT_MODEL[payload.phase]
    flags = UI_STATE_FLAGS[phase]
    question_updates = _question_updates(event)
    current_question = question_updates["current_question"]
    recommended_phase = event.journey_state.recommended_entry_phase or payload.phase
    visual_cue = schema_visual_cue(event)
    support_steps = schema_support_steps(event)
    support_hint = schema_hint(event)
    phase_state = _payload_phase_state(event)
    session = SessionRecord(
        session_id=session_id,
        student_id=request.student_id,
        concept_id=request.concept_id,
        started_at=started_at,
        last_tutor_response_at=started_at,
        current_phase=phase,
        current_question=current_question,
        question_type=question_updates["question_type"],
        question_id=question_updates["question_id"],
        question_number=question_updates.get("question_number", 1),
        correct_answer=question_updates["correct_answer"],
        served_question_ids=question_updates.get("served_question_ids", []),
        interaction_mode=request.interaction_mode,
        ui_state=phase,
        message=(
            _diagnostic_start_message()
            if phase == "DIAGNOSTIC"
            else support_hint or event.routing.reason
        ),
        diagnostic_transition_message=(
            load_phase0_tutor_config().neutral_transition_message
        ),
        diagnostic_transition_messages=(
            load_phase0_tutor_config().neutral_transition_messages
        ),
        show_canvas=flags["show_canvas"],
        show_hint_button=flags["show_hint_button"],
        show_visual_cue=flags["show_visual_cue"] or visual_cue is not None,
        show_scaffold_panel=flags["show_scaffold_panel"] or bool(support_steps),
        scaffold_steps=support_steps,
        allow_text_input=flags["allow_text_input"],
        allow_voice_input=flags["allow_voice_input"],
        hint_count=_restore_counter(phase_state, "current_hint_count", 0),
        attempt_count=_restore_counter(
            phase_state,
            "current_attempt_sequence",
            1,
        ),
        inactivity_policy=inactivity_policy(),
        last_tutor_turn_id=f"TUTOR-{uuid4()}",
        scaffold_step_number=_restore_counter(

            phase_state,
            "current_scaffold_step_number",
            0,
        ),
        rescue_mode_active=payload.payload_type == "RESCUE_AND_FRESH_QUESTION",
        status="started",
        recommended_entry_phase=(
            PHASE_FROM_STUDENT_MODEL[recommended_phase]
            if recommended_phase is not None
            else None
        ),
        student_model_event=event,
        student_model_state=project_student_model_state(event),
    )
    _sessions[session_id] = session
    return session


def _build_content_exhausted_review_summary(
    event: StudentModelSessionEventResponse,
) -> dict[str, object]:
    """Synthesise a minimal review summary when Phase 3 content ran out."""
    js = event.journey_state
    return {
        "summary_id": "SUMMARY-CONTENT-EXHAUSTED",
        "topic_id": js.topic_id,
        "mastery_status": js.mastery_status,
        "phase_3_summary": {
            "verified": js.phase_3_independent_practice.verified_micro_skill_ids,
            "remaining": js.phase_3_independent_practice.remaining_micro_skill_ids,
            "content_exhausted": True,
        },
    }


def _validate_session_opened_payload(
    event: StudentModelSessionEventResponse,
) -> StudentModelPhasePayload:
    payload = event.phase_payload
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no phase payload for SESSION_OPENED.",
        )

    expected_phase = (
        event.journey_state.recommended_entry_phase
        or event.journey_state.current_phase
    )
    if payload.phase != expected_phase:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Student Model returned phase payload {payload.phase}; "
                f"expected effective phase {expected_phase}."
            ),
        )

    expected_types: dict[StudentModelPhase, set[str]] = {
        "PHASE_0_DIAGNOSTIC": {"QUESTION_SET"},
        "PHASE_1_ORIENTATION": {"ORIENTATION_BUNDLE"},
        "PHASE_2_GUIDED_LEARNING": {
            "QUESTION_SET",
            "SUPPORT_AND_RETRY",
            "SCAFFOLD",
            "RESCUE",
        },
        "PHASE_3_INDEPENDENT_PRACTICE": {
            "QUESTION_SET",
            "RESCUE_AND_FRESH_QUESTION",
        },
        "REVIEW": {"REVIEW_SUMMARY"},
    }
    allowed_types = expected_types[payload.phase]
    if payload.payload_type not in allowed_types:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Student Model returned payload type {payload.payload_type} "
                f"for {payload.phase}; expected one of {sorted(allowed_types)}."
            ),
        )
    if payload.payload_type in {
        "QUESTION_SET",
        "SUPPORT_AND_RETRY",
        "SCAFFOLD",
        "RESCUE_AND_FRESH_QUESTION",
    } and (
        payload.question_set is None or not payload.question_set.questions
    ):
        if payload.phase == "PHASE_3_INDEPENDENT_PRACTICE":
            logger.warning(
                "Phase 3 content exhausted — no questions in payload. "
                "Auto-transitioning session to REVIEW phase."
            )
            return StudentModelPhasePayload(
                phase="REVIEW",
                payload_type="REVIEW_SUMMARY",
                review_summary=_build_content_exhausted_review_summary(event),
            )
        raise HTTPException(
            status_code=503,
            detail=f"Student Model returned no questions for {payload.phase}.",
        )
    if payload.payload_type == "ORIENTATION_BUNDLE" and (
        payload.orientation_bundle is None
        or not payload.orientation_bundle.delivery_sequence
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no orientation content.",
        )
    if payload.payload_type in {"SUPPORT_AND_RETRY", "SCAFFOLD"} and (
        payload.support_to_serve is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no guided support content.",
        )
    if payload.payload_type in {"RESCUE", "RESCUE_AND_FRESH_QUESTION"} and (
        payload.rescue_to_serve is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no rescue content.",
        )
    if payload.payload_type == "REVIEW_SUMMARY" and payload.review_summary is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no review summary.",
        )
    return payload


def _schema_session(session_id: str, student_id: str) -> SessionRecord:
    session = _get_owned_session(session_id, student_id)
    if session.student_model_event is None:
        raise HTTPException(
            status_code=409,
            detail=f"Session {session_id} was not initialized through Student Model Schema 3.0.",
        )
    return session


def _schema_request_id(
    session: SessionRecord,
    source_turn_id: str,
    event_type: str,
) -> str:
    if session.student_model_event is None:
        raise RuntimeError("Schema 3.0 request id requires a stored Student Model event.")
    return _student_model_request_id(session.session_id, source_turn_id, event_type)


def _schema_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _question_updates(
    event: StudentModelSessionEventResponse,
) -> QuestionUpdates:
    payload = event.phase_payload
    if payload is None or payload.question_set is None or not payload.question_set.questions:
        return {
            "current_question": None,
            "question_type": None,
            "question_id": None,
            "correct_answer": None,
        }
    current_question_id = _payload_phase_state(event).current_question_id
    questions = payload.question_set.questions
    question_index = 0
    if current_question_id is not None:
        question_index = next(
            (
                index
                for index, question in enumerate(questions)
                if question.question_id == current_question_id
            ),
            -1,
        )
        if question_index == -1:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned current_question_id "
                    f"{current_question_id} outside the {payload.phase} question set."
                ),
            )
    current = questions[question_index]
    return {
        "current_question": current.student_view.question_text,
        "question_type": current.student_view.question_type,
        "question_id": current.question_id,
        "question_number": question_index + 1,
        "correct_answer": current.tutor_view.answer_spec.canonical_answer,
        "served_question_ids": [question.question_id for question in questions],
    }


def _payload_phase_state(
    event: StudentModelSessionEventResponse,
) -> JourneyPhaseState:
    payload = event.phase_payload
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no phase payload.",
        )
    journey = event.journey_state
    phase_states: dict[StudentModelPhase, JourneyPhaseState] = {
        "PHASE_0_DIAGNOSTIC": journey.phase_0_diagnostic,
        "PHASE_1_ORIENTATION": journey.phase_1_orientation,
        "PHASE_2_GUIDED_LEARNING": journey.phase_2_guided_learning,
        "PHASE_3_INDEPENDENT_PRACTICE": journey.phase_3_independent_practice,
        "REVIEW": journey.review,
    }
    return phase_states[payload.phase]


def _restore_counter(
    phase_state: JourneyPhaseState,
    field_name: str,
    offset: int,
) -> int:
    value = (phase_state.model_extra or {}).get(field_name)
    if value is None:
        return 0
    if type(value) is not int or value < offset:
        raise HTTPException(
            status_code=503,
            detail=f"Student Model returned invalid {field_name}: {value}.",
        )
    return value - offset


def _require_schema_phase(
    event: StudentModelSessionEventResponse,
    allowed_phases: tuple[StudentModelPhase, ...],
) -> None:
    payload = event.phase_payload
    if payload is None or payload.phase not in allowed_phases:
        actual_phase = payload.phase if payload is not None else None
        raise HTTPException(
            status_code=503,
            detail=(
                "Student Model returned an unexpected phase "
                f"{actual_phase}; expected one of {allowed_phases}."
            ),
        )


def _apply_schema_event(
    session: SessionRecord,
    event: StudentModelSessionEventResponse,
) -> SessionRecord:
    payload = event.phase_payload
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no phase payload for the active phase.",
        )
    next_phase = PHASE_FROM_STUDENT_MODEL[payload.phase]
    transition = resolve_transition(session.current_phase, next_phase)
    if next_phase != session.current_phase and transition is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Student Model returned an invalid phase transition "
                f"{session.current_phase} -> {next_phase}."
            ),
        )

    has_questions = (
        payload.question_set is not None and bool(payload.question_set.questions)
    )
    if payload.payload_type in {
        "QUESTION_SET",
        "SUPPORT_AND_RETRY",
        "SCAFFOLD",
        "RESCUE_AND_FRESH_QUESTION",
    } and not has_questions:
        raise HTTPException(
            status_code=503,
            detail=(
                "Student Model returned no active question for "
                f"{payload.phase}."
            ),
        )

    preserve_active_question = (
        next_phase == session.current_phase
        and next_phase in {"GUIDED_PRACTICE", "INDEPENDENT_PRACTICE"}
        and payload.payload_type == "RESCUE"
        and not has_questions
    )
    stored_event = event
    if preserve_active_question:
        previous_payload = (
            session.student_model_event.phase_payload
            if session.student_model_event is not None
            else None
        )
        previous_question_set = (
            previous_payload.question_set if previous_payload is not None else None
        )
        if (
            previous_question_set is None
            or session.question_id is None
            or not any(
                question.question_id == session.question_id
                for question in previous_question_set.questions
            )
        ):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned rescue without recoverable active "
                    "question metadata."
                ),
            )
        stored_event = event.model_copy(
            update={
                "phase_payload": payload.model_copy(
                    update={"question_set": previous_question_set}
                )
            }
        )

    flags = UI_STATE_FLAGS[next_phase]
    phase1_messages = load_phase1_tutor_messages()
    question_updates: QuestionUpdates | None = (
        None if preserve_active_question else _question_updates(event)
    )
    updates: dict[str, object] = {
        "current_phase": next_phase,
        "ui_state": next_phase,
        "message": event.routing.reason,
        "recommended_entry_phase": (
            PHASE_FROM_STUDENT_MODEL[event.journey_state.recommended_entry_phase]
            if event.journey_state.recommended_entry_phase is not None
            else None
        ),
        "student_model_event": stored_event,
        "student_model_state": project_student_model_state(event),
        "show_canvas": flags["show_canvas"],
        "show_hint_button": flags["show_hint_button"],
        "show_visual_cue": flags["show_visual_cue"],
        "show_scaffold_panel": flags["show_scaffold_panel"],
        "allow_text_input": flags["allow_text_input"],
        "allow_voice_input": flags["allow_voice_input"],
    }
    if question_updates is not None:
        updates.update(question_updates)
    if next_phase == "CONCEPT_ORIENTATION":
        updates["orientation_messages"] = phase1_messages
        if next_phase == session.current_phase:
            updates["message"] = phase1_messages.before_video_message
    next_question_id = (
        session.question_id
        if question_updates is None
        else question_updates["question_id"]
    )
    if next_question_id != session.question_id:
        updates.update(
            {
                "question_number": (
                    session.question_number + 1
                    if next_question_id is not None
                    else session.question_number
                ),
                "attempt_count": 0,
                "question_completed": next_question_id is None,
                "generated_question_rubric": None,
                "active_teaching_objective": None,
                "guided_student_state": None,
                "selected_error_code": None,
                "wrong_attempt_count": 0,
            }
        )
    if transition is not None:
        updates.update(
            {
                "previous_phase": session.current_phase,
                "attempt_count": 0,
                "question_completed": False,
                "phase_transitions": [
                    *session.phase_transitions,
                    PhaseTransitionRecord(
                        previous_phase=session.current_phase,
                        current_phase=next_phase,
                        entry_reason=event.routing.reason_code,
                        transitioned_at=event.processed_at,
                    ),
                ],
            }
        )
        phase0_config = load_phase0_tutor_config()
        transition_message = (
            _orientation_entry_message(event)
            if (
                session.current_phase == "DIAGNOSTIC"
                and next_phase == "CONCEPT_ORIENTATION"
            )
            else (
                phase0_config.no_gaps_transition_message
                if (
                    session.current_phase == "DIAGNOSTIC"
                    and next_phase == "INDEPENDENT_PRACTICE"
                )
                else TRANSITION_MESSAGES.get((session.current_phase, next_phase))
            )
        )
        if (
            session.current_phase == "CONCEPT_ORIENTATION"
            and next_phase == "GUIDED_PRACTICE"
        ):
            transition_message = phase1_messages.worked_example_to_guided_message
        if transition_message is not None:
            updates["message"] = transition_message
    updated = session.model_copy(update=updates)
    _sessions[session.session_id] = updated
    return updated


def _orientation_entry_message(event: StudentModelSessionEventResponse) -> str:
    messages = load_phase1_tutor_messages()
    payload = event.phase_payload
    bundle = payload.orientation_bundle if payload is not None else None
    if bundle is None:
        return messages.transition_to_orientation_message
    video_count = sum(
        item.content_type == "ORIENTATION_VIDEO"
        for item in bundle.delivery_sequence
    )
    if len(bundle.target_micro_skill_ids) > 1 and video_count == 1:
        return messages.shared_video_transition_message
    return messages.transition_to_orientation_message


def _diagnostic_results(
    session: SessionRecord,
    request: DiagnosticCompleteRequest,
) -> list[MicroSkillResult]:
    event = session.student_model_event
    if event is None or event.phase_payload is None:
        raise RuntimeError("Diagnostic grading requires the stored start event.")
    question_set = event.phase_payload.question_set
    if question_set is None:
        raise HTTPException(status_code=409, detail="No diagnostic question set is active.")

    answers = {answer.question_id: answer.student_response for answer in request.answers}
    if len(answers) != len(request.answers):
        raise HTTPException(status_code=422, detail="Diagnostic question IDs must be unique.")
    questions: dict[str, StudentModelQuestion] = {
        question.question_id: question for question in question_set.questions
    }
    if set(answers) != set(questions):
        raise HTTPException(
            status_code=422,
            detail="Answers must include every served diagnostic question exactly once.",
        )

    results: dict[str, DiagnosticResult] = {}
    for question in question_set.questions:
        answer_spec = question.tutor_view.answer_spec
        if answer_spec.verification_method != "EXACT_CHOICE_MATCH":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Unsupported diagnostic verification method "
                    f"{answer_spec.verification_method} for {question.question_id}."
                ),
            )
        result = (
            "CORRECT"
            if answers[question.question_id] in answer_spec.accepted_answers
            else "INCORRECT"
        )
        for mapping in question.micro_skill_mappings:
            previous = results.get(mapping.micro_skill_id)
            results[mapping.micro_skill_id] = (
                "INCORRECT" if previous == "INCORRECT" or result == "INCORRECT" else "CORRECT"
            )
    expected_skills = set(event.journey_state.phase_0_diagnostic.target_micro_skill_ids)
    if set(results) != expected_skills:
        raise HTTPException(
            status_code=503,
            detail=(
                "Student Model diagnostic questions do not cover the declared "
                "target micro-skills."
            ),
        )
    return [
        MicroSkillResult(micro_skill_id=micro_skill_id, result=result)
        for micro_skill_id, result in results.items()
    ]


async def complete_diagnostic(
    session_id: str,
    request: DiagnosticCompleteRequest,
    access_token: str,
) -> SessionRecord:
    session = _schema_session(session_id, request.student_id)
    if session.current_phase != "DIAGNOSTIC":
        raise HTTPException(status_code=409, detail="The session is not in DIAGNOSTIC.")
    stored_event = session.student_model_event
    if stored_event is None:
        raise RuntimeError("Schema 3.0 session is missing its stored event.")
    event = await get_adapters().student_model.send_session_event(
        DiagnosticCompletedEvent(
            request_id=_schema_request_id(
                session,
                "DIAGNOSTIC_COMPLETED",
                "DIAGNOSTIC_COMPLETED",
            ),
            event_type="DIAGNOSTIC_COMPLETED",
            source_turn_id="DIAGNOSTIC_COMPLETED",
            expected_journey_version=stored_event.journey_state.version,
            topic_id=stored_event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=_schema_timestamp(),
            micro_skill_results=_diagnostic_results(session, request),
        ),
        access_token,
    )
    _require_schema_phase(
        event,
        ("PHASE_1_ORIENTATION", "PHASE_3_INDEPENDENT_PRACTICE"),
    )
    payload = event.phase_payload
    if (
        payload is not None
        and payload.phase == "PHASE_1_ORIENTATION"
        and payload.orientation_bundle is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no orientation bundle.",
        )
    if (
        payload is not None
        and payload.phase == "PHASE_3_INDEPENDENT_PRACTICE"
        and (payload.question_set is None or not payload.question_set.questions)
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no independent-practice questions.",
        )
    return _apply_schema_event(session, event)


def _orientation_targets(session: SessionRecord) -> list[str]:
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Orientation requires a stored Schema 3.0 event.")
    targets = event.journey_state.phase_1_orientation.target_micro_skill_ids
    if not targets:
        raise HTTPException(
            status_code=409,
            detail="Student Model returned no orientation target micro-skills.",
        )
    return targets


def _required_orientation_content(session: SessionRecord) -> tuple[set[str], set[str]]:
    event = session.student_model_event
    payload = event.phase_payload if event is not None else None
    bundle = payload.orientation_bundle if payload is not None else None
    if bundle is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no active orientation bundle.",
        )

    video_ids: list[str] = []
    worked_example_ids: list[str] = []
    for item in bundle.delivery_sequence:
        if item.content_type == "ORIENTATION_VIDEO":
            if item.video is None:
                raise HTTPException(
                    status_code=503,
                    detail="Student Model orientation video item has no video content.",
                )
            video_ids.append(item.video.video_id)
        elif item.content_type == "WORKED_EXAMPLE":
            if item.worked_example is None:
                raise HTTPException(
                    status_code=503,
                    detail="Student Model worked-example item has no worked example content.",
                )
            worked_example_ids.append(item.worked_example.worked_example_id)

    if len(video_ids) != len(set(video_ids)):
        raise HTTPException(
            status_code=503,
            detail="Student Model orientation bundle contains duplicate video IDs.",
        )
    if len(worked_example_ids) != len(set(worked_example_ids)):
        raise HTTPException(
            status_code=503,
            detail="Student Model orientation bundle contains duplicate worked-example IDs.",
        )
    return set(video_ids), set(worked_example_ids)


def _validate_orientation_completion(
    session: SessionRecord,
    request: OrientationCompletionRequest,
) -> None:
    submitted_video_ids = set(request.completed_video_ids)
    submitted_example_ids = set(request.completed_worked_example_ids)
    if len(submitted_video_ids) != len(request.completed_video_ids):
        raise HTTPException(
            status_code=422,
            detail="Completed orientation video IDs must be unique.",
        )
    if len(submitted_example_ids) != len(request.completed_worked_example_ids):
        raise HTTPException(
            status_code=422,
            detail="Completed worked-example IDs must be unique.",
        )

    required_video_ids, required_example_ids = _required_orientation_content(session)
    unknown_video_ids = submitted_video_ids - required_video_ids
    unknown_example_ids = submitted_example_ids - required_example_ids
    if unknown_video_ids or unknown_example_ids:
        raise HTTPException(
            status_code=422,
            detail=(
                "Orientation completion contains content that was not served: "
                f"video_ids={sorted(unknown_video_ids)}, "
                f"worked_example_ids={sorted(unknown_example_ids)}."
            ),
        )

    missing_video_ids = required_video_ids - submitted_video_ids
    missing_example_ids = required_example_ids - submitted_example_ids
    if missing_video_ids or missing_example_ids:
        raise HTTPException(
            status_code=409,
            detail=(
                "Orientation content must be completed before entering Guided Practice: "
                f"missing_video_ids={sorted(missing_video_ids)}, "
                f"missing_worked_example_ids={sorted(missing_example_ids)}."
            ),
        )


async def start_orientation(
    session_id: str,
    request: OrientationPhaseRequest,
    access_token: str,
) -> SessionRecord:
    session = _schema_session(session_id, request.student_id)
    if session.current_phase != "CONCEPT_ORIENTATION":
        raise HTTPException(
            status_code=409,
            detail="The session is not in CONCEPT_ORIENTATION.",
        )
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema 3.0 session is missing its stored event.")
    response = await get_adapters().student_model.send_session_event(
        WorkedExampleRequestedEvent(
            request_id=_schema_request_id(
                session,
                "WORKED_EXAMPLE_REQUESTED",
                "WORKED_EXAMPLE_REQUESTED",
            ),
            event_type="WORKED_EXAMPLE_REQUESTED",
            source_turn_id="WORKED_EXAMPLE_REQUESTED",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=_schema_timestamp(),
            target_micro_skill_ids=_orientation_targets(session),
        ),
        access_token,
    )
    _require_schema_phase(response, ("PHASE_1_ORIENTATION",))
    if (
        response.phase_payload is None
        or response.phase_payload.orientation_bundle is None
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no orientation bundle.",
        )
    return _apply_schema_event(session, response)


async def complete_orientation(
    session_id: str,
    request: OrientationCompletionRequest,
    access_token: str,
) -> SessionRecord:
    session = _schema_session(session_id, request.student_id)
    if session.current_phase != "CONCEPT_ORIENTATION":
        raise HTTPException(
            status_code=409,
            detail="The session is not in CONCEPT_ORIENTATION.",
        )
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema 3.0 session is missing its stored event.")
    if event.journey_state.phase_1_orientation.status != "IN_PROGRESS":
        raise HTTPException(
            status_code=409,
            detail="Orientation must be started before it can be completed.",
        )
    _validate_orientation_completion(session, request)
    response = await get_adapters().student_model.send_session_event(
        OrientationCompletedEvent(
            request_id=_schema_request_id(
                session,
                "ORIENTATION_COMPLETED",
                "ORIENTATION_COMPLETED",
            ),
            event_type="ORIENTATION_COMPLETED",
            source_turn_id="ORIENTATION_COMPLETED",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=_schema_timestamp(),
            target_micro_skill_ids=_orientation_targets(session),
        ),
        access_token,
    )
    _require_schema_phase(response, ("PHASE_2_GUIDED_LEARNING",))
    if (
        response.phase_payload is None
        or response.phase_payload.question_set is None
        or not response.phase_payload.question_set.questions
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no guided-practice questions.",
        )
    return _apply_schema_event(session, response)


async def get_session(session_id: str) -> SessionRecord:
    """Return a stored mock session or raise a standard 404."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None:
        raise _session_not_found(session_id)
    return session


def assemble_session_summary(session: SessionRecord, ended_at: datetime) -> SessionSummary:
    """Build the final summary from recorded session activity."""

    phases_completed: list[Phase] = []
    for transition in session.phase_transitions:
        if transition.previous_phase not in phases_completed:
            phases_completed.append(transition.previous_phase)
    if session.current_phase not in phases_completed:
        phases_completed.append(session.current_phase)

    phase_4_entry_reason: str | None = next(
        (
            transition.entry_reason
            for transition in session.phase_transitions
            if transition.current_phase == "INDEPENDENT_PRACTICE"
        ),
        None,
    )
    correct_attempts: int = sum(
        attempt.evaluation == "CORRECT" for attempt in session.per_question_history
    )
    total_attempts: int = len(session.per_question_history)
    return SessionSummary(
        session_id=session.session_id,
        student_id=session.student_id,
        concept_id=session.concept_id,
        session_date=session.started_at,
        session_duration_seconds=max(0, int((ended_at - session.started_at).total_seconds())),
        interaction_mode=session.interaction_mode,
        phase_4_entry_reason=phase_4_entry_reason,
        phases_completed=phases_completed,
        session_performance=SessionPerformance(
            total_attempts=total_attempts,
            correct_attempts=correct_attempts,
            incorrect_attempts=total_attempts - correct_attempts,
            hints_used=len(session.hint_levels_used),
            hint_levels_used=session.hint_levels_used,
            scaffold_steps_delivered=None,
            canvas_submissions=len(session.canvas_submissions),
        ),
        per_question_history=session.per_question_history,
        scaffold_history=None,
        canvas_feedback_history=[
            submission.tutor.canvas_feedback for submission in session.canvas_submissions
        ],
        phase_transitions=session.phase_transitions,
        recommended_entry_phase=session.recommended_entry_phase,
        conversation_history=session.conversation_history,
    )


_PHASE_WORDS: dict[str, str] = {
    "DIAGNOSTIC": "diagnostic",
    "CONCEPT_ORIENTATION": "concept",
    "GUIDED_PRACTICE": "guided practice",
    "INDEPENDENT_PRACTICE": "independent practice",
    "REVIEW": "review",
}


def _review_hint_level(hint_level: int) -> int | None:
    return min(hint_level, 3) if hint_level > 0 else None


def build_session_review_request(session: SessionRecord) -> "SessionReviewRequest":
    """Map the stored session onto Chirudeva's strict session-review contract.

    Evidence descriptions deliberately contain no digits or question text: the
    review guardrail rejects any evidence that echoes a protected answer, and
    algebra questions can contain their own answer as a coefficient.
    """

    from app.models.session_review import SessionReviewRequest

    attempts: list[dict[str, object]] = []
    attempt_numbers: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    for record in session.per_question_history:
        number = attempt_numbers.get(record.question_id, 0) + 1
        attempt_numbers[record.question_id] = number
        correct = record.evaluation == "CORRECT"
        phase_word = _PHASE_WORDS.get(record.phase, "practice")
        if not correct and record.error_type is not None:
            error_counts[record.error_type] = error_counts.get(record.error_type, 0) + 1
        attempts.append(
            {
                "question_id": record.question_id,
                "phase": record.phase,
                "attempt_number": number,
                "evaluation": record.evaluation,
                "error_type": record.error_type,
                "hint_level_used": _review_hint_level(record.hint_level_used),
                "independent_success": (
                    correct
                    and record.phase == "INDEPENDENT_PRACTICE"
                    and record.hint_level_used == 0
                ),
                "canvas_submitted": record.input_source == "CANVAS",
                "canvas_first_error_step": None,
                "canvas_first_error_type": None,
                "successful_step_descriptions": (
                    [f"Reached the correct final answer on a {phase_word} question"]
                    if correct
                    else []
                ),
                "error_description": (
                    None
                    if correct
                    else f"Did not reach the correct final answer on a {phase_word} question"
                ),
                "rescue_activated": False,
            }
        )
    if not any(attempt["successful_step_descriptions"] for attempt in attempts) and attempts:
        attempts[0]["successful_step_descriptions"] = [
            "Kept attempting every question through the session"
        ]

    correct_attempts = sum(
        record.evaluation == "CORRECT" for record in session.per_question_history
    )
    phases_completed: list[Phase] = []
    for transition in session.phase_transitions:
        if transition.previous_phase not in phases_completed:
            phases_completed.append(transition.previous_phase)
    if session.current_phase not in phases_completed:
        phases_completed.append(session.current_phase)

    student = session.last_student_model
    dominant_error = max(error_counts, key=error_counts.get) if error_counts else None
    recommended = session.recommended_entry_phase
    if recommended not in _PHASE_WORDS:
        recommended = session.current_phase

    return SessionReviewRequest.model_validate(
        {
            "session_summary": {
                "session_id": session.session_id,
                "student_id": session.student_id,
                "concept_id": session.concept_id,
                "session_date": session.started_at.isoformat(),
                "session_duration_seconds": max(
                    0,
                    int((datetime.now(timezone.utc) - session.started_at).total_seconds()),
                ),
                "interaction_mode": session.interaction_mode,
                "phase_4_entry_reason": "normal_review",
                "phases_completed": phases_completed,
                "session_performance": {
                    "total_attempts": len(attempts),
                    "correct_attempts": correct_attempts,
                    "incorrect_attempts": len(attempts) - correct_attempts,
                    "hints_used": len(session.hint_levels_used),
                    "hint_levels_used": [
                        min(level, 3) for level in session.hint_levels_used
                    ],
                    "canvas_submissions": len(session.canvas_submissions),
                    "rescue_mode_activations": int(session.rescue_mode_active),
                    "long_pressure_events": 0,
                    "voice_fallback_events": 0,
                },
                "per_question_history": attempts,
                "canvas_feedback_history": [],
                "phase_transitions": [
                    {
                        "from_phase": transition.previous_phase,
                        "to_phase": transition.current_phase,
                        "timestamp": transition.transitioned_at.isoformat(),
                    }
                    for transition in session.phase_transitions
                ],
            },
            "student_model": {
                "mastery_status": student.mastery_status if student else "DEVELOPING",
                "error_counts": error_counts,
                "dominant_error_type": dominant_error,
                "hint_dependency_score": (
                    student.hint_dependency_score if student else 0.0
                ),
                "error_confirmed_pattern": False,
                "recommended_entry_phase": recommended,
                "next_concept_recommendation": None,
            },
        }
    )


async def end_session(request: SessionEndRequest) -> SessionRecord:
    """Generate the engine review, then mark a stored mock session as ended.

    Review generation runs first: if it fails (or the session has no graded
    attempts), the caller gets an explicit error and the session stays active.
    """

    # Imported here: ai_engine.session_review imports this module for answers.
    from pydantic import ValidationError

    from app.ai_engine.session_review import (
        SessionReviewValidationError,
        generate_session_review,
    )

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    if len(session.per_question_history) == 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot end the session yet: no graded attempts to review.",
        )
    try:
        review = generate_session_review(build_session_review_request(session))
    except (SessionReviewValidationError, ValidationError, RuntimeError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Session review could not be generated; the session is still active. ({error})",
        ) from error

    summary: SessionSummary = assemble_session_summary(session, datetime.now(timezone.utc))
    ended_session: SessionRecord = session.model_copy(
        update={
            "status": "ended",
            "message": "Session ended.",
            "session_summary": summary,
            "session_review": review,
        }
    )
    _sessions[request.session_id] = ended_session
    clear_nudge_deliveries_for_session(request.session_id)
    return ended_session


def start_voice_stream(session_id: str, student_id: str) -> SessionRecord:
    """Mark the voice stream active for an existing session."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )

    voice_state: VoiceState = session.voice_state.model_copy(
        update={
            "stream_active": True,
            "current_turn": "STUDENT",
            "fallback_active": False,
        }
    )
    updated_session: SessionRecord = session.model_copy(update={"voice_state": voice_state})
    _sessions[session_id] = updated_session
    return updated_session


async def record_canvas_submission(
    session_id: str,
    student_id: str,
    session: SessionRecord,
    record: CanvasSubmissionRecord,
    conversation_history: list[ConversationMessage],
    last_student_model: StudentModelResult | None,
) -> SessionRecord:
    """Append a reviewed canvas submission without replacing Schema 3.0 state."""

    if session.session_id != session_id or session.student_id != student_id:
        raise ValueError("Canvas session identity does not match the request.")
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )

    per_question_history: list[QuestionAttemptRecord] = session.per_question_history
    if record.tutor.evaluation != "UNCLEAR":
        if session.question_id is None or session.current_question is None:
            raise HTTPException(
                status_code=409,
                detail="The current phase has no active question.",
            )
        per_question_history = [
            *per_question_history,
            QuestionAttemptRecord(
                question_id=session.question_id,
                question_text=session.current_question,
                phase=session.current_phase,
                evaluation=record.tutor.evaluation,
                error_type=(
                    record.tutor.error_type
                    if record.tutor.evaluation != "CORRECT"
                    else None
                ),
                input_source="CANVAS",
                hint_level_used=record.tutor.hint_level,
                attempted_at=record.submitted_at,
            ),
        ]
    updated_session: SessionRecord = session.model_copy(
        update={
            "canvas_submissions": [*session.canvas_submissions, record],
            # Schema 3.0 state was applied before this canvas record is stored.
            # Keep those fields authoritative; the tutor result is descriptive.
            "attempt_count": session.attempt_count,
            "question_completed": session.question_completed,
            "answer_value_confirmed": session.answer_value_confirmed,
            "conversation_history": conversation_history,
            "per_question_history": per_question_history,
            "recommended_entry_phase": session.recommended_entry_phase,
            "last_student_model": last_student_model or session.last_student_model,
        }
    )
    # This read-modify-write is safe only while the mock backend uses one worker.
    _sessions[session_id] = updated_session
    return updated_session


async def record_canvas_attachment(
    session_id: str,
    student_id: str,
    record: CanvasSubmissionRecord,
) -> SessionRecord:
    """Store voice-attached OCR without counting a second student attempt."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )
    updated_session: SessionRecord = session.model_copy(
        update={"canvas_submissions": [*session.canvas_submissions, record]}
    )
    _sessions[session_id] = updated_session
    return updated_session


def get_canvas_submission(
    session: SessionRecord,
    submission_id: str | None,
) -> CanvasSubmissionRecord | None:
    """Return a session-owned canvas submission by its public identifier."""

    if submission_id is None:
        return None
    return next(
        (
            submission
            for submission in session.canvas_submissions
            if submission.submission_id == submission_id
        ),
        None,
    )


def update_interaction_state(
    session_id: str,
    student_id: str,
    session: SessionRecord,
    current_phase: Phase,
    hint_count: int,
    ui_state: str,
    transcript_confidence: float | None,
    canvas_snapshot_id: str | None,
    ocr_result: VisionOCRResult | None,
    show_visual_cue: bool,
    show_scaffold_panel: bool,
    scaffold_steps: list[str],
    transition_updates: dict[str, object],
) -> SessionRecord:
    """Update frontend-facing session state after one interaction turn.

    transition_updates is the per-turn state overlay (attempt counter,
    question completion, 6.7 transition/question-advance keys); it is merged
    last so it wins.
    """

    if session.session_id != session_id or session.student_id != student_id:
        raise ValueError("Interaction session identity does not match the request.")
    voice_state: VoiceState = session.voice_state.model_copy(
        update={"last_transcript_confidence": transcript_confidence}
    )
    canvas_state: CanvasState = session.canvas_state.model_copy(
        update={
            "snapshot_id": canvas_snapshot_id,
            "ocr_result": ocr_result,
        }
    )
    updated_session: SessionRecord = session.model_copy(
        update={
            "current_phase": current_phase,
            "ui_state": ui_state,
            "hint_count": hint_count,
            "voice_state": voice_state,
            "canvas_state": canvas_state,
            # Phase-driven flags first; the tutor's per-turn cue/scaffold
            # outputs then override their always-False map entries.
            **UI_STATE_FLAGS[current_phase],
            "show_visual_cue": show_visual_cue,
            "show_scaffold_panel": show_scaffold_panel,
            "scaffold_steps": scaffold_steps,
            **transition_updates,
        }
    )
    _sessions[session_id] = updated_session
    return updated_session
