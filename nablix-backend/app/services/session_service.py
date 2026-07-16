from datetime import datetime, timezone

from fastapi import HTTPException

from app.adapters.question_bank import fetch_question
from app.core.config import get_settings
from app.core.exceptions import QuestionFetchError
from app.models.adapters import ConversationMessage, StudentModelResult, VisionOCRResult
from app.models.canvas import CanvasSubmissionRecord
from app.models.fields import Phase
from app.models.session import (
    CanvasState,
    QuestionAttemptRecord,
    SessionEndRequest,
    SessionPerformance,
    SessionRecord,
    SessionStartRequest,
    SessionSummary,
    VoiceState,
)
from app.services.phase_transition import UI_STATE_FLAGS


_sessions: dict[str, SessionRecord] = {}
_next_session_number: int = 1


def _build_session_id() -> str:
    global _next_session_number

    if _next_session_number > 999:
        raise RuntimeError("mock session id range exhausted at SESSION999.")

    session_id: str = f"SESSION{_next_session_number:03d}"
    _next_session_number += 1
    return session_id


def _session_not_found(session_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"Session with ID {session_id} was not found.",
    )


# Single source of truth for demo questions: question_id -> (question, answer, number).
# Adding one here feeds both the prompt (start_session) and grading (correct_answer_for),
# so the two can't drift. Replace with a real question bank when one exists.
_DEMO_QUESTIONS: dict[str, tuple[str, str, int]] = {
    "ALG_EQ_DIAG_001": ("Solve for x: x + 4 = 9", "x = 5", 1),
    "ALG_EQ_CO_001": ("Solve for x: x - 3 = 7", "x = 10", 1),
    "ALG_EQ_GP_001": ("Solve for x: x + 6 = 10", "x = 4", 1),
    "ALG_EQ_IP_001": ("Solve for x: 3x + 2 = 11", "x = 3", 1),
    "ALG_EQ_REV_001": ("Solve for x: x / 2 = 8", "x = 16", 1),
}
_DEFAULT_QUESTION_ID = "ALG_EQ_DIAG_001"
_DEMO_STUDENT_ID = "ST001"

# Answers of knowledge-base questions served this process, so lookups by bare
# question_id (e.g. session review) keep working for non-demo questions.
_served_answers: dict[str, str] = {}


def correct_answer_for(question_id: str) -> str | None:
    """Return the expected answer for a question_id, or None if unknown."""

    served = _served_answers.get(question_id)
    if served is not None:
        return served
    entry = _DEMO_QUESTIONS.get(question_id)
    return entry[1] if entry else None


def _mock_diagnostic_question() -> tuple[str, str, int]:
    """Return the first diagnostic question as (question, question_id, number).

    Placeholder for Aditya's POST /diagnostic/question.
    """

    question, _answer, number = _DEMO_QUESTIONS[_DEFAULT_QUESTION_ID]
    return (question, _DEFAULT_QUESTION_ID, number)


async def get_next_question(
    concept_id: str,
    phase: Phase,
    served_question_ids: list[str] | None = None,
    difficulty: str = "FOUNDATION",
) -> tuple[str, str, str] | None:
    """Return (question_text, correct_answer, question_id) or None when exhausted.

    Questions come directly from the Qdrant knowledge base. None means the
    caller must fail loudly, never continue silently.
    """

    settings = get_settings()
    if settings.qdrant_url == "" or settings.qdrant_api_key == "":
        raise QuestionFetchError(concept_id, phase)
    fetched = await fetch_question(concept_id, phase, served_question_ids, difficulty)
    if fetched is not None:
        _served_answers[fetched[2]] = fetched[1]
    return fetched


def _diagnostic_start_message(question: str) -> str:
    """Return the frontend intro message for the first diagnostic question."""

    spoken_question: str = question.replace("+", "plus").replace("=", "equals")
    return (
        "Let us start with a quick question to see where you are. "
        f"{spoken_question}."
    )


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
    """Recover request-carried demo state when Vercel starts a new instance."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None and student_id == _DEMO_STUDENT_ID:
        session = _recover_demo_session(session_id, student_id, current_phase, hint_count)
    if session is None or session.student_id != student_id:
        raise _session_not_found(session_id)
    return session


def _recover_demo_session(
    session_id: str,
    student_id: str,
    current_phase: Phase,
    hint_count: int,
) -> SessionRecord:
    """Rebuild the fixed demo session after Vercel drops in-memory state."""

    question, question_id, question_number = _mock_diagnostic_question()
    # ponytail: demo-only stateless recovery; replace _sessions with real storage for multi-user deploys.
    session = SessionRecord(
        session_id=session_id,
        student_id=student_id,
        concept_id="ALG_LINEAR_ONE_STEP",
        started_at=datetime.now(timezone.utc),
        interaction_mode="VOICE",
        current_phase=current_phase,
        current_question=question,
        question_id=question_id,
        question_number=question_number,
        correct_answer=correct_answer_for(question_id),
        served_question_ids=[question_id],
        ui_state=current_phase,
        hint_count=hint_count,
        status="started",
        message=_diagnostic_start_message(question),
        show_hint_button=UI_STATE_FLAGS[current_phase]["show_hint_button"],
    )
    _sessions[session_id] = session
    return session


async def start_session(request: SessionStartRequest) -> SessionRecord:
    """Create and store the mock session response used before real persistence exists."""

    initial_phase: Phase = (
        request.initial_phase if request.initial_phase is not None else "GUIDED_PRACTICE"
    )
    fetched = await get_next_question(request.concept_id, initial_phase)
    if fetched is None:
        raise QuestionFetchError(request.concept_id, initial_phase)
    question, correct_answer, question_id = fetched
    session: SessionRecord = SessionRecord(
        session_id=_build_session_id(),
        student_id=request.student_id,
        concept_id=request.concept_id,
        started_at=datetime.now(timezone.utc),
        interaction_mode=request.interaction_mode,
        current_phase=initial_phase,
        current_question=question,
        question_id=question_id,
        question_number=1,
        correct_answer=correct_answer,
        served_question_ids=[question_id],
        ui_state=initial_phase,
        hint_count=0,
        status="started",
        message=_diagnostic_start_message(question),
        show_hint_button=UI_STATE_FLAGS[initial_phase]["show_hint_button"],
    )
    _sessions[session.session_id] = session
    return session


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
    record: CanvasSubmissionRecord,
    attempt_count: int,
    question_completed: bool,
    conversation_history: list[ConversationMessage],
    recommended_entry_phase: str | None,
    last_student_model: StudentModelResult | None = None,
) -> SessionRecord:
    """Append a reviewed canvas submission and persist its attempt count."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )

    per_question_history: list[QuestionAttemptRecord] = session.per_question_history
    if record.tutor.evaluation != "UNCLEAR":
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
            "attempt_count": attempt_count,
            "question_completed": question_completed,
            "conversation_history": conversation_history,
            "per_question_history": per_question_history,
            "recommended_entry_phase": recommended_entry_phase,
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


def increment_hint_count(session_id: str) -> int:
    """Bump the stored hint count for a session and return the new value."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None:
        raise _session_not_found(session_id)
    new_count = session.hint_count + 1
    _sessions[session_id] = session.model_copy(
        update={
            "hint_count": new_count,
            "hint_levels_used": [*session.hint_levels_used, new_count],
        }
    )
    return new_count


def restore_interaction_progress(
    session_id: str,
    student_id: str,
    attempt_count: int | None,
    question_completed: bool | None,
    conversation_history: list[ConversationMessage],
) -> SessionRecord:
    """Apply orchestration-owned progress after stateless session recovery."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    updates: dict[str, object] = {}
    if attempt_count is not None:
        updates["attempt_count"] = max(session.attempt_count, attempt_count)
    if question_completed is not None:
        updates["question_completed"] = session.question_completed or question_completed
    if len(conversation_history) > 0:
        updates["conversation_history"] = conversation_history
    if len(updates) == 0:
        return session
    updated_session: SessionRecord = session.model_copy(update=updates)
    _sessions[session_id] = updated_session
    return updated_session


def update_interaction_state(
    session_id: str,
    student_id: str,
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

    session: SessionRecord = _get_owned_session(session_id, student_id)
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
