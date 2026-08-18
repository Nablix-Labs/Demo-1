from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.auth import AccessToken
from app.models.interaction import (
    InteractionRequest,
    InteractionResponse,
    StaleTurnResponse,
)
from app.services.interaction_service import process_interaction

router = APIRouter()


@router.post(
    "/interaction",
    response_model=InteractionResponse,
    responses={409: {"model": StaleTurnResponse}},
)
async def interaction_endpoint(
    request: InteractionRequest,
    access_token: AccessToken,
) -> InteractionResponse | JSONResponse:
    if (
        request.input_source == "VOICE"
        and request.interaction_type == "ANSWER_SUBMISSION"
        and request.canvas_state is None
    ):
        raise HTTPException(
            status_code=422,
            detail="canvas_state is required for REST VOICE answer submissions.",
        )
    response = await process_interaction(request, access_token)
    if isinstance(response, StaleTurnResponse):
        return JSONResponse(status_code=409, content=response.model_dump())
    return response
