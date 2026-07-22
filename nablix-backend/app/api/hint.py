from fastapi import APIRouter

from app.api.auth import AccessToken
from app.models.hint import HintRequest, HintResponse
from app.services.hint_service import process_hint

router = APIRouter()


@router.post("/request", response_model=HintResponse)
async def hint_request_endpoint(
    request: HintRequest,
    access_token: AccessToken,
) -> HintResponse:
    return await process_hint(request, access_token)
