from fastapi import APIRouter

from app.api.auth import AccessToken
from app.models.fields import SessionId, StudentId
from app.models.session import (
    DiagnosticCompleteRequest,
    OrientationCompletionRequest,
    OrientationPhaseRequest,
    ReviewCompleteRequest,
    RescueAdvanceRequest,
    RescueRenderAckRequest,
    RescueStepResponse,
    SessionResumeRequest,
    SessionEndRequest,
    SessionRecord,
    SessionResponse,
    SessionStartRequest,
)
from app.services.session_service import (
    complete_diagnostic,
    complete_orientation,
    complete_review,
    acknowledge_rescue_render,
    advance_rescue,
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


# Retired (ADR 0004), kept for one release so an older client is told why
# rather than shown a 404 it will read as a lost session.
@router.post("/{session_id}/resume", response_model=SessionResponse, deprecated=True)
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


@router.post("/{session_id}/rescue/render-ack", response_model=RescueStepResponse)
async def acknowledge_rescue_render_endpoint(
    session_id: SessionId,
    request: RescueRenderAckRequest,
    access_token: AccessToken,
) -> RescueStepResponse:
    return await acknowledge_rescue_render(session_id, request, access_token)


@router.post("/{session_id}/rescue/advance", response_model=RescueStepResponse)
async def advance_rescue_endpoint(
    session_id: SessionId,
    request: RescueAdvanceRequest,
    access_token: AccessToken,
) -> RescueStepResponse:
    return await advance_rescue(session_id, request)


@router.post("/end", response_model=SessionResponse)
async def end_session_endpoint(request: SessionEndRequest) -> SessionRecord:
    return await end_session(request)
