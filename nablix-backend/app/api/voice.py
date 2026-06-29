from fastapi import APIRouter

from app.models.interaction import InteractionResponse
from app.models.voice import (
    VoiceRequest,
    VoiceResponse,
    VoiceSessionStartRequest,
    VoiceSessionStartResponse,
    VoiceTranscriptRequest,
)
from app.services.voice_service import (
    process_voice,
    process_voice_transcript,
    start_voice_session,
)

router = APIRouter()


@router.post("", response_model=VoiceResponse)
async def voice_endpoint(request: VoiceRequest) -> VoiceResponse:
    return await process_voice(request)


@router.post("/session/start", response_model=VoiceSessionStartResponse)
async def voice_session_start_endpoint(
    request: VoiceSessionStartRequest,
) -> VoiceSessionStartResponse:
    return await start_voice_session(request)


@router.post("/transcript", response_model=InteractionResponse)
async def voice_transcript_endpoint(
    request: VoiceTranscriptRequest,
) -> InteractionResponse:
    return await process_voice_transcript(request)
