from fastapi import HTTPException

from app.models.adapters import VisionOCRResult
from app.models.canvas import CanvasSubmissionRecord
from app.models.fields import Phase
from app.models.session import (
    CanvasState,
    SessionEndRequest,
    SessionRecord,
    SessionStartRequest,
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

# Aditya stub data: (concept_id, phase) -> question_id into _DEMO_QUESTIONS.
_PHASE_QUESTION_IDS: dict[tuple[str, Phase], str] = {
    ("ALG_LINEAR_ONE_STEP", "DIAGNOSTIC"): "ALG_EQ_DIAG_001",
    ("ALG_LINEAR_ONE_STEP", "CONCEPT_ORIENTATION"): "ALG_EQ_CO_001",
    ("ALG_LINEAR_ONE_STEP", "GUIDED_PRACTICE"): "ALG_EQ_GP_001",
    ("ALG_LINEAR_ONE_STEP", "INDEPENDENT_PRACTICE"): "ALG_EQ_IP_001",
    ("ALG_LINEAR_ONE_STEP", "REVIEW"): "ALG_EQ_REV_001",
}


def correct_answer_for(question_id: str) -> str | None:
    """Return the expected answer for a question_id, or None if unknown."""

    entry = _DEMO_QUESTIONS.get(question_id)
    return entry[1] if entry else None


def _mock_diagnostic_question() -> tuple[str, str, int]:
    """Return the first diagnostic question as (question, question_id, number).

    Placeholder for Aditya's POST /diagnostic/question.
    """

    question, _answer, number = _DEMO_QUESTIONS[_DEFAULT_QUESTION_ID]
    return (question, _DEFAULT_QUESTION_ID, number)


def get_next_question(
    concept_id: str,
    phase: Phase,
    previous_question_id: str | None = None,
    difficulty: str = "FOUNDATION",
) -> tuple[str, str, str] | None:
    """Aditya stub: return (question_text, correct_answer, question_id).

    Placeholder for Aditya's POST /question/next. Returns None when Aditya
    has nothing for the concept/phase — the caller must fail loudly, never
    continue silently.
    # ponytail: previous_question_id/difficulty accepted per contract but
    # ignored (one question per phase); honor them when a real bank exists.
    """

    question_id = _PHASE_QUESTION_IDS.get((concept_id, phase))
    if question_id is None:
        return None
    question, answer, _number = _DEMO_QUESTIONS[question_id]
    return (question, answer, question_id)


def _diagnostic_start_message(question: str) -> str:
    """Return the frontend intro message for the first diagnostic question."""

    spoken_question: str = question.replace("+", "plus").replace("=", "equals")
    return (
        "Let us start with a quick question to see where you are. "
        f"{spoken_question}."
    )


def _get_owned_session(session_id: str, student_id: str) -> SessionRecord:
    """Return the session owned by the student or raise a standard 404."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None and student_id == _DEMO_STUDENT_ID:
        session = _recover_demo_session(session_id, student_id)
    if session is None or session.student_id != student_id:
        raise _session_not_found(session_id)
    return session


def _recover_demo_session(session_id: str, student_id: str) -> SessionRecord:
    """Rebuild the fixed demo session after Vercel drops in-memory state."""

    question, question_id, question_number = _mock_diagnostic_question()
    # ponytail: demo-only stateless recovery; replace _sessions with real storage for multi-user deploys.
    session = SessionRecord(
        session_id=session_id,
        student_id=student_id,
        concept_id="ALG_LINEAR_ONE_STEP",
        interaction_mode="VOICE",
        current_phase="GUIDED_PRACTICE",
        current_question=question,
        question_id=question_id,
        question_number=question_number,
        ui_state="GUIDED_PRACTICE",
        hint_count=0,
        status="started",
        message=_diagnostic_start_message(question),
        show_hint_button=UI_STATE_FLAGS["GUIDED_PRACTICE"]["show_hint_button"],
    )
    _sessions[session_id] = session
    return session


async def start_session(request: SessionStartRequest) -> SessionRecord:
    """Create and store the mock session response used before real persistence exists."""

    question, question_id, question_number = _mock_diagnostic_question()
    initial_phase: Phase = request.initial_phase if request.initial_phase is not None else "DIAGNOSTIC"
    session: SessionRecord = SessionRecord(
        session_id=_build_session_id(),
        student_id=request.student_id,
        concept_id=request.concept_id,
        interaction_mode=request.interaction_mode,
        current_phase=initial_phase,
        current_question=question,
        question_id=question_id,
        question_number=question_number,
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


async def end_session(request: SessionEndRequest) -> SessionRecord:
    """Mark a stored mock session as ended."""

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    ended_session: SessionRecord = session.model_copy(
        update={
            "status": "ended",
            "message": "Session ended.",
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
) -> SessionRecord:
    """Append a canvas OCR record to an active mock session."""

    session: SessionRecord = _get_owned_session(session_id, student_id)
    if session.status == "ended":
        raise HTTPException(
            status_code=409,
            detail=f"Session with ID {session_id} has ended.",
        )

    updated_session: SessionRecord = session.model_copy(
        update={"canvas_submissions": [*session.canvas_submissions, record]}
    )
    # This read-modify-write is safe only while the mock backend uses one worker.
    _sessions[session_id] = updated_session
    return updated_session


def increment_hint_count(session_id: str) -> int:
    """Bump the stored hint count for a session and return the new value."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None:
        raise _session_not_found(session_id)
    new_count = session.hint_count + 1
    _sessions[session_id] = session.model_copy(update={"hint_count": new_count})
    return new_count


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
    transition_updates: dict[str, object] | None = None,
) -> SessionRecord:
    """Update frontend-facing session state after one interaction turn.

    transition_updates is the 6.7 phase-transition overlay (previous_phase,
    new question, counter resets); it is merged last so it wins.
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
            **(transition_updates or {}),
        }
    )
    _sessions[session_id] = updated_session
    return updated_session
