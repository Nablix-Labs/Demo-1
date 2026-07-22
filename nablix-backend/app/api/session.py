from fastapi import APIRouter
from fastapi import HTTPException

from app.ai_engine.session_review import (
    QuestionAnswerNotFoundError,
    SessionReviewValidationError,
    generate_session_review,
)
from app.models.fields import SessionId
from app.models.session import SessionEndRequest, SessionRecord, SessionStartRequest
from app.models.session_review import SessionReviewRequest, SessionReviewResponse
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


@router.post("/review/generate", response_model=SessionReviewResponse)
async def generate_session_review_endpoint(
    request: SessionReviewRequest,
) -> SessionReviewResponse:
    try:
        return generate_session_review(request)
    except QuestionAnswerNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SessionReviewValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
