from fastapi import APIRouter

from app.api.auth import AccessToken
from app.models.canvas import CanvasSubmitRequest
from app.models.interaction import InteractionResponse
from app.services.canvas_service import submit_canvas
from app.services.session_service import interaction_lock_for

router = APIRouter()


@router.post("/submit", response_model=InteractionResponse)
async def canvas_submit_endpoint(
    request: CanvasSubmitRequest,
    access_token: AccessToken,
) -> InteractionResponse:
    async with interaction_lock_for(request.session_id):
        return await submit_canvas(request, access_token)
