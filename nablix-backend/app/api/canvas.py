from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.auth import AccessToken
from app.models.canvas import CanvasSubmitRequest
from app.models.interaction import InteractionResponse, StaleTurnResponse
from app.services.canvas_service import submit_canvas
from app.services.session_service import interaction_lock_for

router = APIRouter()


@router.post(
    "/submit",
    response_model=InteractionResponse,
    responses={409: {"model": StaleTurnResponse}},
)
async def canvas_submit_endpoint(
    request: CanvasSubmitRequest,
    access_token: AccessToken,
) -> InteractionResponse | JSONResponse:
    async with interaction_lock_for(request.session_id):
        response = await submit_canvas(request, access_token)
    if isinstance(response, StaleTurnResponse):
        return JSONResponse(status_code=409, content=response.model_dump(mode="json"))
    return response
