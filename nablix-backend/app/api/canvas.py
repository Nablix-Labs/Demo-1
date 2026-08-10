from fastapi import APIRouter

from app.api.auth import AccessToken
from app.models.canvas import CanvasSubmitRequest
from app.models.interaction import InteractionResponse
from app.services.canvas_service import submit_canvas

router = APIRouter()


@router.post("/submit", response_model=InteractionResponse)
async def canvas_submit_endpoint(
    request: CanvasSubmitRequest,
    access_token: AccessToken,
) -> InteractionResponse:
    return await submit_canvas(request, access_token)
