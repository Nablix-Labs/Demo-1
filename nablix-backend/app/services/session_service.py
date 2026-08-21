import asyncio
from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from typing_extensions import NotRequired

from app.adapters.provider import get_adapters
from app.core.config import get_settings
from app.core.exceptions import DOWNSTREAM_FAILURE, JourneyVersionConflict
from app.core.logger import logger
from app.ai_engine.phase4_review import generate_phase4_review
from app.models.phase4_review import Phase4ReviewResponse, QuestionJourneyItem
from app.models.work_artifact import Phase4ReviewPersistRequest
from app.services.phase4_context_builder import build_phase4_review_request
from app.services.phase4_replay_filter import PHASE_3, filter_replay_attempts
from app.models.adapters import ConversationMessage, StudentModelResult, VisualCue, VisionOCRResult
from app.models.canvas import CanvasQuestionMemory, CanvasStroke, CanvasSubmissionRecord
from app.models.canvas_memory import CanvasEvent
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
    ReviewCompleteRequest,
    SessionEndRequest,
    SessionPerformance,
    SessionRecord,
    SessionStartRequest,
    SessionResumeRequest,
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
    ReviewCompletedEvent,
    SessionOpenedEvent,
    SessionResumedEvent,
    StudentModelJourneyState,
    StudentModelPhasePayload,
    StudentModelPhase,
    StudentModelQuestion,
    StudentModelSessionEventResponse,
    WorkedExampleRequestedEvent,
)
from app.services.guided_question_opening import guided_question_opening
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
from app.services.session_store import save_session


_sessions: dict[str, SessionRecord] = {}
_interaction_locks: dict[str, asyncio.Lock] = {}
_last_interaction_responses: dict[tuple[str, str], InteractionResponse] = {}
_interaction_payload_fingerprints: dict[tuple[str, str], str] = {}
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
    payload_fingerprint: str,
) -> None:
    _last_interaction_responses[(session_id, turn_id)] = response
    _interaction_payload_fingerprints[(session_id, turn_id)] = payload_fingerprint


def interaction_payload_fingerprint_for(session_id: str, turn_id: str) -> str | None:
    return _interaction_payload_fingerprints.get((session_id, turn_id))


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
    "last_nudge_generated_at",
    "pending_nudge_id",
    "pending_nudge_message",
}


async def update_side_channel_state(
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
    await save_session(updated)
    return updated


async def store_prerequisite_repair_event(
    session: SessionRecord,
    event: StudentModelSessionEventResponse,
) -> SessionRecord:
    updated = session.model_copy(update={"prerequisite_repair_event": event})
    _sessions[session.session_id] = updated
    await save_session(updated)
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


def _skip_journey_reconcile(session_id: str, student_id: str, reason: str) -> None:
    """Log why a 409 could not self-heal the session's cached journey state.

    These conflicts otherwise leave no trace, which is the gap that made the
    original loop so hard to diagnose. An identity mismatch is not routine: it
    means the Student Model's conflict body named a different student or topic
    than the session it was raised for.
    """

    logger.warning(
        "journey_conflict_reconcile_skipped",
        extra={"session_id": session_id, "student_id": student_id, "reason": reason},
    )


async def reconcile_journey_conflict(
    session_id: str,
    student_id: str,
    conflict: JourneyVersionConflict,
) -> None:
    """Sync a session's cached journey state after the Student Model rejects it.

    The Student Model's 409 carries the journey it actually holds. Without this,
    a session that fell behind (e.g. another session for the same student/topic
    advanced it) resends the same stale expected_journey_version forever, since
    nothing refreshes the cache that value is read from. Best-effort: anything
    that stops it just leaves the existing 409 to reach the client unchanged.
    """

    session = _sessions.get(session_id)
    if session is None or session.student_id != student_id:
        _skip_journey_reconcile(session_id, student_id, "session_not_found_or_not_owned")
        return
    event = session.student_model_event
    if event is None:
        _skip_journey_reconcile(session_id, student_id, "schema_3_state_missing")
        return

    detail = conflict.conflict_detail
    if not isinstance(detail, dict):
        _skip_journey_reconcile(session_id, student_id, "conflict_detail_not_a_dict")
        return
    # Two raise sites, two shapes: the true 409 nests the journey under
    # current_journey_state, while a 200 carrying a conflict status passes the
    # whole response, where it sits under journey_state.
    raw_journey = detail.get("current_journey_state", detail.get("journey_state"))
    if not isinstance(raw_journey, dict):
        _skip_journey_reconcile(session_id, student_id, "no_journey_state_in_conflict")
        return

    try:
        fresh_journey = StudentModelJourneyState.model_validate(raw_journey)
    except ValidationError:
        _skip_journey_reconcile(session_id, student_id, "journey_state_failed_validation")
        return
    if (
        fresh_journey.student_id != student_id
        or fresh_journey.topic_id != event.journey_state.topic_id
    ):
        _skip_journey_reconcile(session_id, student_id, "journey_state_identity_mismatch")
        return
    if fresh_journey.version <= event.journey_state.version:
        _skip_journey_reconcile(session_id, student_id, "journey_state_not_newer")
        return

    # Take the fresh version AND drop everything derived from the stale one. The
    # 409 body carries journey_state only - no phase_payload - so the question,
    # answer spec and served ids cannot be refreshed from it. Keeping them would
    # splice the new journey onto the old question: a state the Student Model
    # never held, and one that would submit already-used evidence against a
    # version that now accepts it. Clearing them re-arms
    # _initialize_restored_schema_phase, which every answer path runs first and
    # which re-derives the whole envelope at the corrected version.
    #
    # phase_payload must go too: that restore path re-applies the stored event
    # when its payload still carries questions, handing the stale question
    # straight back. Dropping it forces a real question-set request.
    updated = session.model_copy(
        update={
            "student_model_event": event.model_copy(
                update={"journey_state": fresh_journey, "phase_payload": None}
            ),
            "current_phase": PHASE_FROM_STUDENT_MODEL[fresh_journey.current_phase],
            "current_question": None,
            "question_id": None,
            "question_type": None,
            "correct_answer": None,
            "active_student_model_question": None,
        }
    )
    _sessions[session_id] = updated
    await save_session(updated)
    logger.info(
        "journey_conflict_reconciled",
        extra={
            "session_id": session_id,
            "student_id": student_id,
            "stale_version": event.journey_state.version,
            "authoritative_version": fresh_journey.version,
        },
    )


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
    if payload.phase != event.phase_payload.phase:
        event = event.model_copy(update={"phase_payload": payload})
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
            "Session Review — practice questions complete."
            if phase == "REVIEW"
            else _diagnostic_start_message()
            if phase == "DIAGNOSTIC"
            else guided_question_opening(
                current_question,
                question_updates["question_type"],
                "Let’s resume with this question.",
            )
            if (
                phase == "GUIDED_PRACTICE"
                and current_question is not None
                and support_hint is None
            )
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
        active_visual_cue=visual_cue,
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
        active_student_model_question=(
            payload.question_set.questions[0]
            if payload.question_set is not None and payload.question_set.questions
            else None
        ),
    )
    _sessions[session_id] = session
    await save_session(session)
    return session


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
    if payload.phase != expected_phase and not (
        expected_phase == "PHASE_3_INDEPENDENT_PRACTICE" and payload.phase == "REVIEW"
    ):
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
            return payload
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


async def generate_phase4_review_for(
    session: SessionRecord,
    event: StudentModelSessionEventResponse,
) -> Phase4ReviewResponse | None:
    """Review the finished topic as the student enters Phase 4.

    A failure here must not strand the student outside Review, so the phase
    transition still happens and the review is simply absent; the frontend
    shows the topic outcome without a tutor replay.
    """

    try:
        history = await get_adapters().student_model.fetch_topic_event_history(
            session.student_id,
            event.journey_state.topic_id,
        )
        request = build_phase4_review_request(
            history,
            filter_replay_attempts(history.attempts),
            event.journey_state.mastery_status,
            event.routing.next_action,
        )
        review = generate_phase4_review(request)
    # ValueError covers Phase4ContextError, Phase4ReviewValidationError and
    # pydantic's ValidationError, so malformed evidence degrades to no review
    # rather than stranding the student outside Review.
    except (*DOWNSTREAM_FAILURE, ValueError) as error:
        logger.warning(
            "phase4_review_not_generated",
            extra={
                "session_id": session.session_id,
                "topic_id": event.journey_state.topic_id,
                "status_code": getattr(error, "status_code", None),
                "error": str(error),
            },
        )
        return None

    # Deterministic fields the model was never asked for: forwarded straight
    # from the request that was just built, not generated.
    replay_context_by_id = {item.review_item_id: item for item in request.replay_items}
    review = review.model_copy(
        update={
            "tutor_replays": [
                replay.model_copy(
                    update={
                        "question_text": replay_context_by_id[replay.review_item_id].question_text,
                        "work_artifact": replay_context_by_id[replay.review_item_id].work_artifact,
                    }
                )
                if replay.review_item_id in replay_context_by_id
                else replay
                for replay in review.tutor_replays
            ],
            "topic_outcome": request.topic_outcome,
            "question_journey": [
                QuestionJourneyItem(
                    question_id=attempt.question_id,
                    evaluation=attempt.evaluation,
                    hint_used=attempt.hint_used,
                    independent_success=attempt.independent_success,
                    attempted_at=attempt.attempted_at,
                )
                for attempt in history.attempts
                if attempt.phase == PHASE_3
            ],
        }
    )

    try:
        await get_adapters().student_model.persist_phase4_review(
            Phase4ReviewPersistRequest(
                student_id=session.student_id,
                topic_id=event.journey_state.topic_id,
                tutor_replays=[
                    replay.model_dump(mode="json") for replay in review.tutor_replays
                ],
                student_insights=review.student_insights.model_dump(mode="json"),
            ),
        )
    except DOWNSTREAM_FAILURE as error:
        # The review is already generated; the student should still see it
        # even if it could not be stored for reuse.
        logger.warning(
            "phase4_review_not_persisted",
            extra={
                "session_id": session.session_id,
                "topic_id": event.journey_state.topic_id,
                "status_code": getattr(error, "status_code", None),
                "error": str(error),
            },
        )
    return review


async def _apply_schema_event(
    session: SessionRecord,
    event: StudentModelSessionEventResponse,
) -> SessionRecord:
    payload = event.phase_payload
    has_questions = (
        payload is not None
        and payload.question_set is not None
        and bool(payload.question_set.questions)
    )
    if payload is not None and payload.payload_type in {
        "QUESTION_SET",
        "SUPPORT_AND_RETRY",
        "SCAFFOLD",
        "RESCUE_AND_FRESH_QUESTION",
    } and not has_questions:
        if payload.phase != "PHASE_3_INDEPENDENT_PRACTICE":
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned no active question for "
                    f"{payload.phase}."
                ),
            )

    next_phase = PHASE_FROM_STUDENT_MODEL[
        payload.phase if payload is not None else event.journey_state.current_phase
    ]
    transition = resolve_transition(session.current_phase, next_phase)
    if next_phase != session.current_phase and transition is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Student Model returned an invalid phase transition "
                f"{session.current_phase} -> {next_phase}."
            ),
        )

    preserve_active_question = (
        next_phase == session.current_phase
        and next_phase in {"GUIDED_PRACTICE", "INDEPENDENT_PRACTICE"}
        and payload is not None
        and payload.payload_type == "RESCUE"
        and not has_questions
    )
    previous_used_ids = (
        session.student_model_event.journey_state.phase_3_independent_practice.used_question_ids
        if session.student_model_event is not None
        else []
    )
    if payload is not None and payload.phase == "PHASE_3_INDEPENDENT_PRACTICE" and payload.question_set is not None:
        reused_ids = [
            question.question_id
            for question in payload.question_set.questions
            if question.question_id in previous_used_ids
        ]
        if reused_ids:
            raise HTTPException(
                status_code=503,
                detail=f"Student Model returned previously used fresh questions: {reused_ids}.",
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
        "student_model_event": event,
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
        if payload is not None and payload.question_set is not None and payload.question_set.questions:
            current_question_id = question_updates["question_id"]
            updates["active_student_model_question"] = next(
                question
                for question in payload.question_set.questions
                if question.question_id == current_question_id
            )
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
                "attempt_count": 0,
                "question_completed": next_question_id is None,
                "generated_question_rubric": None,
                "active_teaching_objective": None,
                "guided_teaching_state": None,
                "guided_student_state": None,
                "selected_error_code": None,
                "wrong_attempt_count": 0,
                "canvas_state": session.canvas_state.model_copy(
                    update={"snapshot_id": None, "ocr_result": None}
                ),
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
        if next_phase == "REVIEW":
            updates["phase4_review"] = await generate_phase4_review_for(
                session,
                event,
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
    if (
        next_phase == "GUIDED_PRACTICE"
        and next_question_id is not None
        and next_question_id != session.question_id
        and question_updates is not None
    ):
        next_question = question_updates["current_question"]
        if next_question is None:
            raise RuntimeError("Guided Practice question is missing its text.")
        updates["message"] = guided_question_opening(
            next_question,
            question_updates["question_type"],
            str(updates["message"]),
        )
    updated = session.model_copy(update=updates)
    _sessions[session.session_id] = updated
    await save_session(updated)
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
    return await _apply_schema_event(session, event)


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
    return await _apply_schema_event(session, response)


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
    return await _apply_schema_event(session, response)


async def get_session(session_id: str, student_id: str) -> SessionRecord:
    """Return a session only when it belongs to the requesting student."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None or session.student_id != student_id:
        raise _session_not_found(session_id)
    return session


async def resume_session(
    session_id: str,
    request: SessionResumeRequest,
    access_token: str,
) -> SessionRecord:
    session = _schema_session(session_id, request.student_id)
    stored_event = session.student_model_event
    if stored_event is None:
        raise RuntimeError("Schema session is missing its Student Model event.")
    request_id = _schema_request_id(session, request.turn_id, "SESSION_RESUMED")
    if stored_event.request_id == request_id:
        return session
    last_activity_at = request.last_activity_at or session.last_tutor_response_at
    event = SessionResumedEvent(
        request_id=request_id,
        event_type="SESSION_RESUMED",
        source_turn_id=request.turn_id,
        expected_journey_version=stored_event.journey_state.version,
        topic_id=stored_event.journey_state.topic_id,
        student_id=session.student_id,
        timestamp=_schema_timestamp(),
        last_activity_at=last_activity_at.isoformat().replace("+00:00", "Z"),
        continuity_threshold_days=(
            request.continuity_threshold_days
            or get_settings().resume_continuity_threshold_days
        ),
        saved_journey=(
            request.saved_journey
            if request.saved_journey is not None
            else stored_event.journey_state.model_dump(mode="json")
        ),
    )
    response = await get_adapters().student_model.send_session_event(event, access_token)
    return await _apply_schema_event(session, response)


async def complete_review(
    session_id: str,
    request: ReviewCompleteRequest,
    access_token: str,
) -> SessionRecord:
    session = _schema_session(session_id, request.student_id)
    if session.current_phase != "REVIEW":
        raise HTTPException(status_code=409, detail="The session is not in Review.")
    stored_event = session.student_model_event
    if stored_event is None:
        raise RuntimeError("Schema session is missing its Student Model event.")
    request_id = _schema_request_id(session, request.turn_id, "REVIEW_COMPLETED")
    if stored_event.request_id == request_id:
        return session
    response = await get_adapters().student_model.send_session_event(
        ReviewCompletedEvent(
            request_id=request_id,
            event_type="REVIEW_COMPLETED",
            source_turn_id=request.turn_id,
            expected_journey_version=stored_event.journey_state.version,
            topic_id=stored_event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=_schema_timestamp(),
        ),
        access_token,
    )
    return await _apply_schema_event(session, response)


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


async def end_session(request: SessionEndRequest) -> SessionRecord:
    """Mark a stored session as ended without generating a legacy review."""

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    summary: SessionSummary = assemble_session_summary(session, datetime.now(timezone.utc))
    ended_session: SessionRecord = session.model_copy(
        update={
            "status": "ended",
            "message": "Session ended.",
            "session_summary": summary,
        }
    )
    _sessions[request.session_id] = ended_session
    await save_session(ended_session)
    clear_nudge_deliveries_for_session(request.session_id)
    return ended_session


async def start_voice_stream(session_id: str, student_id: str) -> SessionRecord:
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
    await save_session(updated_session)
    return updated_session


async def record_canvas_submission(
    session_id: str,
    student_id: str,
    session: SessionRecord,
    turn_session: SessionRecord,
    record: CanvasSubmissionRecord,
    conversation_history: list[ConversationMessage],
    last_student_model: StudentModelResult | None,
    strokes: list[CanvasStroke],
    canvas_events: list[CanvasEvent],
    work_artifact_id: str | None = None,
) -> SessionRecord:
    """Append a reviewed canvas submission without replacing Schema 3.0 state."""

    if (
        session.session_id != session_id
        or session.student_id != student_id
        or turn_session.session_id != session_id
        or turn_session.student_id != student_id
    ):
        raise ValueError("Canvas session identity does not match the request.")
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )

    per_question_history: list[QuestionAttemptRecord] = session.per_question_history
    if record.tutor.evaluation != "UNCLEAR":
        if turn_session.question_id is None or turn_session.current_question is None:
            raise HTTPException(
                status_code=409,
                detail="The current phase has no active question.",
            )
        per_question_history = [
            *per_question_history,
            QuestionAttemptRecord(
                question_id=turn_session.question_id,
                question_text=turn_session.current_question,
                phase=turn_session.current_phase,
                evaluation=record.tutor.evaluation,
                error_type=(
                    record.tutor.error_type
                    if record.tutor.evaluation != "CORRECT"
                    else None
                ),
                input_source="CANVAS",
                hint_level_used=record.tutor.hint_level,
                attempted_at=record.submitted_at,
                work_artifact_id=work_artifact_id,
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
            **build_canvas_memory_update(
                session,
                turn_session.question_id,
                record.submission_id,
                strokes,
                canvas_events,
            ),
            "canvas_state": session.canvas_state.model_copy(
                update={
                    "snapshot_id": (
                        record.submission_id
                        if session.question_id == turn_session.question_id
                        else None
                    ),
                    "ocr_result": (
                        record.ocr
                        if session.question_id == turn_session.question_id
                        else None
                    ),
                }
            ),
        }
    )
    # This read-modify-write is safe only while the mock backend uses one worker.
    _sessions[session_id] = updated_session
    await save_session(updated_session)
    return updated_session


async def record_canvas_attachment(
    session_id: str,
    student_id: str,
    record: CanvasSubmissionRecord,
    strokes: list[CanvasStroke],
    canvas_events: list[CanvasEvent],
) -> SessionRecord:
    """Store voice-attached OCR without counting a second student attempt."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )
    updated_session: SessionRecord = session.model_copy(
        update={
            "canvas_submissions": [*session.canvas_submissions, record],
            **build_canvas_memory_update(
                session,
                session.question_id,
                record.submission_id,
                strokes,
                canvas_events,
            ),
            "canvas_state": session.canvas_state.model_copy(
                update={
                    "snapshot_id": record.submission_id,
                    "ocr_result": record.ocr,
                }
            ),
        }
    )
    _sessions[session_id] = updated_session
    await save_session(updated_session)
    return updated_session


def build_canvas_memory_update(
    session: SessionRecord,
    question_id: str | None,
    turn_id: str,
    strokes: list[CanvasStroke],
    canvas_events: list[CanvasEvent],
) -> dict[str, object]:
    if question_id is None:
        return {}
    return {
        "canvas_memory_by_question": {
            **session.canvas_memory_by_question,
            question_id: CanvasQuestionMemory(
                updated_turn_id=turn_id,
                strokes=strokes,
                canvas_events=canvas_events,
            ),
        }
    }


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


async def update_interaction_state(
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
    next_question_id = transition_updates.get("question_id", session.question_id)
    question_changed = next_question_id != session.question_id
    canvas_state: CanvasState = session.canvas_state.model_copy(
        update={
            "snapshot_id": None if question_changed else canvas_snapshot_id,
            "ocr_result": None if question_changed else ocr_result,
        }
    )
    requested_active_visual_cue = transition_updates.get(
        "active_visual_cue",
        session.active_visual_cue,
    )
    if requested_active_visual_cue is not None and not isinstance(
        requested_active_visual_cue,
        VisualCue,
    ):
        raise ValueError("active_visual_cue must be a VisualCue or None.")
    active_visual_cue = (
        None
        if current_phase != "GUIDED_PRACTICE" or question_changed
        else requested_active_visual_cue
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
            "show_visual_cue": active_visual_cue is not None,
            "active_visual_cue": active_visual_cue,
            "show_scaffold_panel": show_scaffold_panel,
            "scaffold_steps": scaffold_steps,
            **transition_updates,
        }
    )
    _sessions[session_id] = updated_session
    await save_session(updated_session)
    return updated_session
