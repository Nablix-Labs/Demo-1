from fastapi import APIRouter

from app.api.auth import AccessToken
from app.models.canvas import CanvasSubmitRequest, CanvasSubmitResponse
from app.services.canvas_service import submit_canvas

router = APIRouter()


@router.post("/submit", response_model=CanvasSubmitResponse)
async def canvas_submit_endpoint(
    request: CanvasSubmitRequest,
    access_token: AccessToken,
) -> CanvasSubmitResponse:
    return await submit_canvas(request, access_token)
