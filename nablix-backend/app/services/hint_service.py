from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.models.adapters import AdapterContext, StudentModelEvent
from app.models.fields import Phase
from app.models.hint import HintRequest, HintResponse
from app.models.session import SessionRecord
from app.services.interaction_service import _current_hint_level_from, run_tutor_pipeline
from app.services.session_service import _get_owned_session, correct_answer_for, increment_hint_count


_HINT_PHASES: frozenset[Phase] = frozenset(("GUIDED_PRACTICE", "INDEPENDENT_PRACTICE"))


def _validate_hint_phase(request_phase: Phase, stored_phase: Phase) -> None:
    if request_phase not in _HINT_PHASES:
        raise HTTPException(
            status_code=409,
            detail=f"Hints are not available during {request_phase}.",
        )
    if stored_phase not in _HINT_PHASES:
        raise HTTPException(
            status_code=409,
            detail=f"Session phase {stored_phase} does not allow hints.",
        )
    if request_phase != stored_phase:
        raise HTTPException(
            status_code=409,
            detail=f"Request phase {request_phase} does not match session phase {stored_phase}.",
        )


def _validate_hint_count(request_count: int, stored_count: int) -> None:
    if request_count != stored_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f"current_hint_count {request_count} does not match "
                f"stored hint count {stored_count}."
            ),
        )


async def process_hint(request: HintRequest) -> HintResponse:
    """Create a short hint response using the shared tutor pipeline.

    The next hint level is the current count plus one (guide 6.4). The hint text
    comes from the tutor pipeline; the session's stored hint count is bumped.
    """

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    _validate_hint_phase(request.current_phase, session.current_phase)
    _validate_hint_count(request.current_hint_count, session.hint_count)

    next_hint_level: int = session.hint_count + 1
    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        message=f"Hint request for {request.question_id} ({request.concept_id}).",
        question=session.current_question,
        correct_answer=correct_answer_for(request.question_id),
        current_phase=request.current_phase,
        input_source="TEXT",
        attempt_count=next_hint_level,
        current_hint_level=_current_hint_level_from(session.hint_count),
        concept_id=request.concept_id,
    )
    _, _, tutor = await run_tutor_pipeline(context)
    adapters = get_adapters()
    await adapters.student_model.update_from_event(
        StudentModelEvent(
            event_type="HINT_REQUESTED",
            evaluation=tutor.evaluation,
            error_type=tutor.error_type,
            hint_level_used=next_hint_level,
            independent_success=False,
        )
    )
    stored_hint_count: int = increment_hint_count(request.session_id)
    if stored_hint_count != next_hint_level:
        raise RuntimeError(
            f"stored hint count {stored_hint_count} did not match next hint level {next_hint_level}."
        )

    return HintResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        hint_level=next_hint_level,
        hint=tutor.tutor_message,
        response_strategy=tutor.response_strategy,
        answer_reveal_allowed=tutor.answer_reveal_allowed,
    )
