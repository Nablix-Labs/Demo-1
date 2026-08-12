from fastapi import APIRouter
from fastapi import HTTPException

from app.ai_engine.session_review import (
    QuestionAnswerNotFoundError,
    SessionReviewValidationError,
    generate_session_review,
)
from app.api.auth import AccessToken
from app.models.fields import SessionId, StudentId
from app.models.session import (
    DiagnosticCompleteRequest,
    OrientationCompletionRequest,
    OrientationPhaseRequest,
    ReviewCompleteRequest,
    SessionResumeRequest,
    SessionEndRequest,
    SessionRecord,
    SessionResponse,
    SessionStartRequest,
)
from app.models.session_review import SessionReviewRequest, SessionReviewResponse
from app.services.session_service import (
    complete_diagnostic,
    complete_orientation,
    complete_review,
    end_session,
    get_session,
    resume_session,
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
async def get_session_endpoint(
    session_id: SessionId,
    student_id: StudentId,
    access_token: AccessToken,
) -> SessionRecord:
    return await get_session(session_id, student_id)


@router.post("/{session_id}/resume", response_model=SessionResponse)
async def resume_session_endpoint(
    session_id: SessionId,
    request: SessionResumeRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await resume_session(session_id, request, access_token)


@router.post("/{session_id}/review/complete", response_model=SessionResponse)
async def complete_review_endpoint(
    session_id: SessionId,
    request: ReviewCompleteRequest,
    access_token: AccessToken,
) -> SessionRecord:
    return await complete_review(session_id, request, access_token)


@router.post("/end", response_model=SessionResponse)
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
