from fastapi import APIRouter

from app.models.fields import SessionId
from app.models.session import SessionEndRequest, SessionRecord, SessionStartRequest
from app.services.session_service import end_session, get_session, start_session

router = APIRouter()


@router.post("/start", response_model=SessionRecord)
async def start_session_endpoint(request: SessionStartRequest) -> SessionRecord:
    return await start_session(request)


@router.get("/{session_id}", response_model=SessionRecord)
async def get_session_endpoint(session_id: SessionId) -> SessionRecord:
    return await get_session(session_id)


@router.post("/end", response_model=SessionRecord)
async def end_session_endpoint(request: SessionEndRequest) -> SessionRecord:
    return await end_session(request)
