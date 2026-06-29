from fastapi import APIRouter

from app.models.hint import HintRequest, HintResponse
from app.services.hint_service import process_hint

router = APIRouter()


@router.post("/request", response_model=HintResponse)
async def hint_request_endpoint(request: HintRequest) -> HintResponse:
    return await process_hint(request)
