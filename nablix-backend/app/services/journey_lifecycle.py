"""Session and journey recovery lifecycle routines.

Handles restoring phases, recovering pending support events, and handling
Student Model content gaps without re-querying or corrupting journey states.
"""

from datetime import datetime, timezone
from typing import NoReturn

from fastapi import HTTPException

from app.adapters.base import StudentModelAdapter
from app.adapters.provider import get_adapters
from app.ai_engine.classifier_config import load_classifier_rules
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.fields import Phase
from app.models.session import SessionRecord
from app.models.student_model_session import (
    GuidedQuestionSetRequestedEvent,
    IndependentQuestionSetRequestedEvent,
    JourneyPhaseState,
    Phase2RepairResult,
    SessionOpenedEvent,
    StudentModelPhasePayload,
    StudentModelSessionEventResponse,
)
from app.services.rescue_presentation import guided_rescue, presented_rescue
from app.services.session_service import (
    CONTENT_GAP_MESSAGE,
    _apply_schema_event,
    _question_updates,
    get_session,
    interaction_lock_for,
    resume_guided_progression,
)
from app.services.student_model_session import PHASE_FROM_STUDENT_MODEL


def restore_failure_reason(
    payload: StudentModelPhasePayload | None,
    session_phase: Phase,
    effective_phase: str,
    initialized_state: JourneyPhaseState,
) -> str | None:
    """Which of the restore checks rejected this response, or None if it passed.

    Ordered, and each check assumes the ones above it passed -- so this is a
    sequence of guards rather than a table: `payload.phase` cannot be read
    until `payload is None` has been ruled out.
    """
    if payload is None:
        return "MISSING_PAYLOAD"
    if PHASE_FROM_STUDENT_MODEL[payload.phase] != session_phase:
        return "PHASE_MISMATCH"
    if payload.phase != effective_phase:
        return "EFFECTIVE_PHASE_MISMATCH"
    if payload.payload_type != "QUESTION_SET":
        return "WRONG_PAYLOAD_TYPE"
    if payload.question_set is None or not payload.question_set.questions:
        return "NO_QUESTIONS"
    if initialized_state.status == "NOT_STARTED":
        return "PHASE_NOT_STARTED"
    return None


def raise_content_gap(
    session: SessionRecord,
    event: StudentModelSessionEventResponse,
) -> NoReturn:
    """Report a Student Model content gap as itself, not as a restore failure.

    FRESH_CONTENT_UNAVAILABLE is an authoritative answer -- the question does
    not exist -- so it must never be re-requested in a loop, and never be
    laundered into MASTERED, REVIEW, or a Phase 4 review. CONTENT_GAP is a
    stable code the client can branch on -- nothing in Numera-ui reads it yet;
    the previous 503 said only "did not initialize", which nothing could.
    """
    logger.warning(
        "restore_phase_content_gap",
        extra={
            "session_id": session.session_id,
            "phase": session.current_phase,
            "journey_version": event.journey_state.version,
            "reason_code": event.routing.reason_code,
            "next_action": event.routing.next_action,
            "status_code": event.status.status_code,
            "missing_micro_skill_ids": event.routing.missing_micro_skill_ids,
        },
    )
    raise HTTPException(
        status_code=409,
        detail={"code": "CONTENT_GAP", "message": CONTENT_GAP_MESSAGE},
    )


def with_served_rung(
    session: SessionRecord, event: StudentModelSessionEventResponse,
) -> SessionRecord:
    """Attach the support rung `event` re-serves, so applying it keeps the rung.

    The answer spec comes from the INCOMING event, not the session: on a restore
    the session's own copy is the stale one this event is replacing.
    """
    rescue = guided_rescue(event)
    if rescue is None:
        return session
    question = _question_updates(event)
    active = presented_rescue(
        session,
        question["question_id"] or session.question_id,
        rescue,
        question["correct_answer"] or session.correct_answer or "",
        event.request_id,
        load_classifier_rules(),
    )
    return session if active is None else session.model_copy(
        update={"active_guided_rescue": active}
    )


async def apply_restored_event(
    session: SessionRecord, event: StudentModelSessionEventResponse,
) -> SessionRecord:
    """Apply a restore response, keeping any rung it re-serves.

    SESSION_OPENED now answers with the rung the student is actually on -- a
    RESCUE payload for Parallel Example and Tutor-Solved, carrying the question
    with it. Applying only the journey and the question handed the student their
    question back with the walkthrough silently dropped, which is the same rung
    loss this whole change exists to end, one layer further out.

    Best-effort, unlike resume_pending_support: nothing upstream moved to record
    this rung, and GET /session is the one route the client is told to call to
    recover. Failing it outright over a presentation it can re-request on the
    next turn would strand the student completely.
    """
    try:
        session = with_served_rung(session, event)
    except (HTTPException, AdapterError) as error:
        logger.warning(
            "restored_rung_presentation_failed",
            extra={
                "session_id": session.session_id,
                "question_id": session.question_id,
                "request_id": event.request_id,
                "detail": getattr(error, "detail", str(error)),
            },
        )
    return await _apply_schema_event(session, event)


async def resume_pending_support(
    session: SessionRecord, access_token: str,
) -> SessionRecord:
    """Re-serve the support rung whose visual presentation failed to build.

    Student Model answers an already-processed request_id with its original
    envelope, so this rebuilds the rung from the SAME response the failed turn
    received. Nothing is re-decided, no attempt is re-graded, and the escalation
    is never re-chosen against the journey it already advanced.

    A rebuild that fails again propagates: the pending event stays set, the
    session stays blocked, and the student is told why rather than being handed
    a question no submission will be accepted against.
    """
    event = session.pending_support_event
    if event is None:
        raise RuntimeError("Session has no pending support event.")
    response = await get_adapters().student_model.send_session_event(event, access_token)
    return await _apply_schema_event(with_served_rung(session, response), response)


async def initialize_restored_schema_phase(
    session: SessionRecord,
    student_model: StudentModelAdapter,
    access_token: str,
    for_read: bool = False,
) -> SessionRecord:
    """Restore the authoritative question for a phase that lost its cursor.

    `for_read` distinguishes the two callers a content gap has to answer
    differently. A submission cannot be graded against a question that does not
    exist, so it is refused with the explicit CONTENT_GAP code; a GET is the one
    request that is supposed to *show* the pause, so it returns the persisted
    paused session instead. Either way the gap is persisted first, which is what
    stops the next call asking for the same missing content again.
    """
    event = session.student_model_event
    if event is None:
        return session

    payload = event.phase_payload
    if session.journey_recovery_required:
        phase = event.journey_state.recommended_entry_phase or event.journey_state.current_phase
        guided = event.journey_state.phase_2_guided_learning
        if phase != "PHASE_2_GUIDED_LEARNING" or guided.status != "NOT_STARTED":
            # Deterministic on (session, stale version): a retry after a lost
            # response re-asks the identical question instead of booking a new
            # one. SESSION_OPENED is read-only upstream, so a replay is free.
            response = await student_model.send_session_event(SessionOpenedEvent(
                request_id=f"{session.session_id}:RECOVER-{event.journey_state.version}",
                event_type="SESSION_OPENED", topic_id=event.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ), access_token)
            if response.status.success is False:
                raise HTTPException(status_code=503, detail=response.status.intervention_reason)
            return await apply_restored_event(session, response)
    if (
        (session.current_question is None or session.question_id is None)
        and payload is not None
        and payload.question_set is not None
        and payload.question_set.questions
    ):
        session = await _apply_schema_event(session, event)

    # The stored event already said the content does not exist. Asking again
    # returns the same gap, and the answer used to arrive as an opaque 503.
    if (
        session.current_question is None or session.question_id is None
    ) and event.routing.content_gap_detected:
        if for_read:
            return session
        raise_content_gap(session, event)

    if session.current_phase == "GUIDED_PRACTICE":
        phase_state = event.journey_state.phase_2_guided_learning
        missing_question = session.current_question is None or session.question_id is None
        if phase_state.status != "NOT_STARTED" and not missing_question:
            return session

        target_micro_skill_ids = (
            phase_state.target_micro_skill_ids
            if phase_state.status == "NOT_STARTED"
            else phase_state.remaining_micro_skill_ids
        )
        if not target_micro_skill_ids:
            if not missing_question:
                return session
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned an active Guided Practice journey "
                    "without a question or remaining target skills."
                ),
            )
        request = GuidedQuestionSetRequestedEvent(
            request_id=(
                f"{session.session_id}:RESTORE-{event.journey_state.version}:"
                "GUIDED_QUESTION_SET_REQUESTED"
            ),
            event_type="GUIDED_QUESTION_SET_REQUESTED",
            source_turn_id=f"RESTORE-{event.journey_state.version}",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            target_micro_skill_ids=target_micro_skill_ids,
        )
    elif session.current_phase == "INDEPENDENT_PRACTICE":
        phase_state = event.journey_state.phase_3_independent_practice
        missing_question = session.current_question is None or session.question_id is None
        if phase_state.status != "NOT_STARTED" and not missing_question:
            return session

        target_micro_skill_ids = (
            phase_state.target_micro_skill_ids
            if phase_state.status == "NOT_STARTED"
            else phase_state.remaining_micro_skill_ids
        )
        if not target_micro_skill_ids:
            if not missing_question:
                return session
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned an active Independent Practice journey "
                    "without a question or remaining target skills."
                ),
            )

        support_by_skill = (
            event.journey_state.phase_2_guided_learning.highest_support_used_by_skill
        )
        request = IndependentQuestionSetRequestedEvent(
            request_id=(
                f"{session.session_id}:RESTORE-{event.journey_state.version}:"
                "INDEPENDENT_QUESTION_SET_REQUESTED"
            ),
            event_type="INDEPENDENT_QUESTION_SET_REQUESTED",
            source_turn_id=f"RESTORE-{event.journey_state.version}",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            phase2_repair_results=[
                Phase2RepairResult(
                    micro_skill_id=micro_skill_id,
                    highest_support_used=support_by_skill.get(micro_skill_id, "NONE"),
                )
                for micro_skill_id in target_micro_skill_ids
            ],
            used_question_ids=phase_state.used_question_ids,
        )
    else:
        return session

    response = await student_model.send_session_event(request, access_token)
    payload = response.phase_payload
    effective_phase = (
        response.journey_state.recommended_entry_phase
        or response.journey_state.current_phase
    )
    initialized_state = (
        response.journey_state.phase_2_guided_learning
        if session.current_phase == "GUIDED_PRACTICE"
        else response.journey_state.phase_3_independent_practice
    )
    if response.routing.content_gap_detected:
        # Persist the pause before answering: the flags now live on the session,
        # so neither this caller nor the next one re-requests the same content
        # (the ST017 run asked twice, versions 12 then 13).
        paused = await _apply_schema_event(session, response)
        if for_read:
            return paused
        raise_content_gap(paused, response)
    failure_reason = restore_failure_reason(
        payload, session.current_phase, effective_phase, initialized_state
    )
    if failure_reason is not None:
        # Enough to tell these six causes apart in production without carrying
        # answers, tokens, or request bodies into the log.
        logger.error(
            "restore_phase_not_initialized",
            extra={
                "session_id": session.session_id,
                "journey_version": response.journey_state.version,
                "phase": session.current_phase,
                "payload_phase": None if payload is None else payload.phase,
                "payload_type": None if payload is None else payload.payload_type,
                "question_count": (
                    0
                    if payload is None or payload.question_set is None
                    else len(payload.question_set.questions)
                ),
                "current_question_id": session.question_id,
                "effective_phase": effective_phase,
                "initialized_status": initialized_state.status,
                "failure_reason": failure_reason,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Student Model did not initialize the restored phase with questions.",
        )
    return await apply_restored_event(session, response)


async def recover_session_for_read(
    session_id: str, student_id: str, access_token: str,
) -> SessionRecord:
    """Recover only pending work; an ordinary GET never selects new questions."""
    async with interaction_lock_for(session_id):
        session = await get_session(session_id, student_id)
        if session.pending_guided_progression is not None:
            return await resume_guided_progression(session, access_token)
        if session.pending_support_event is not None:
            return await resume_pending_support(session, access_token)
        if session.journey_recovery_required:
            return await initialize_restored_schema_phase(
                session, get_adapters().student_model, access_token, for_read=True
            )
        return session
