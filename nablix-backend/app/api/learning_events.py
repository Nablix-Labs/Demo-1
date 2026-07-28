from fastapi import APIRouter

from app.adapters.provider import get_adapters
from app.api.auth import AccessToken
from app.models.student_model import StudentModelSessionEvent, StudentModelSessionResponse


router = APIRouter()


@router.post("/learning-events", response_model=StudentModelSessionResponse)
async def learning_event_endpoint(
    event: StudentModelSessionEvent,
    access_token: AccessToken,
) -> StudentModelSessionResponse:
    del access_token
    adapters = get_adapters()
    return await adapters.student_model.send_session_event(event)
