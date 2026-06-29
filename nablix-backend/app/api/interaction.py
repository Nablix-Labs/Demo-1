from fastapi import APIRouter

from app.models.interaction import InteractionRequest, InteractionResponse
from app.services.interaction_service import process_interaction

router = APIRouter()


@router.post("/interaction", response_model=InteractionResponse)
async def interaction_endpoint(request: InteractionRequest) -> InteractionResponse:
    return await process_interaction(request)
