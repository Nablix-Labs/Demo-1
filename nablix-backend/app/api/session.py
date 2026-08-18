from fastapi import APIRouter
from fastapi import HTTPException

from app.api.auth import AccessToken
from app.models.fields import SessionId
from app.models.session import (
    DiagnosticCompleteRequest,
    OrientationCompletionRequest,
    OrientationPhaseRequest,
    SessionEndRequest,
    SessionRecord,
    SessionResponse,
    SessionStartRequest,
)
from app.services.session_service import (
    complete_diagnostic,
    complete_orientation,
    end_session,
    get_session,
    start_orientation,
    start_session,
)

router = APIRouter()


@router.post("/start", response_model=SessionResponse)
async def start_session_endpoint(
    request: SessionStartRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await start_session(request, access_token)


@router.post("/{session_id}/diagnostic/complete", response_model=SessionResponse)
async def complete_diagnostic_endpoint(
    session_id: SessionId,
    request: DiagnosticCompleteRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await complete_diagnostic(session_id, request, access_token)


@router.post("/{session_id}/orientation/start", response_model=SessionResponse)
async def start_orientation_endpoint(
    session_id: SessionId,
    request: OrientationPhaseRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await start_orientation(session_id, request, access_token)


@router.post("/{session_id}/orientation/complete", response_model=SessionResponse)
async def complete_orientation_endpoint(
    session_id: SessionId,
    request: OrientationCompletionRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await complete_orientation(session_id, request, access_token)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_endpoint(session_id: SessionId) -> SessionRecord:
    return await get_session(session_id)


@router.post("/end", response_model=SessionResponse)
async def end_session_endpoint(request: SessionEndRequest) -> SessionRecord:
    return await end_session(request)
