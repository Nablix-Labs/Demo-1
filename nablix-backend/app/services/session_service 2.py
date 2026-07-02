from typing import Literal

from fastapi import HTTPException

from app.core.config import get_settings
from app.models.canvas import CanvasSubmissionRecord
from app.models.session import SessionEndRequest, SessionRecord, SessionStartRequest


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


def _get_owned_session(session_id: str, student_id: str) -> SessionRecord:
    """Return the session owned by the student or raise a standard 404."""

    session: SessionRecord | None = _sessions.get(session_id)
    if session is None or session.student_id != student_id:
        raise _session_not_found(session_id)
    return session


async def start_session(request: SessionStartRequest) -> SessionRecord:
    """Create and store the mock session response used before real persistence exists."""

    settings = get_settings()
    mode: Literal["mock", "live"] = "mock" if settings.use_mock_tutor else "live"
    session: SessionRecord = SessionRecord(
        session_id=_build_session_id(),
        student_id=request.student_id,
        topic=request.topic,
        grade_level=request.grade_level,
        status="started",
        mode=mode,
        message="Session started.",
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
