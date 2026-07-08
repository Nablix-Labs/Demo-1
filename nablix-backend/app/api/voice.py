from fastapi import APIRouter, WebSocket

from app.models.interaction import InteractionResponse
from app.models.voice import (
    VoiceRequest,
    VoiceResponse,
    VoiceSessionStartRequest,
    VoiceSessionStartResponse,
    VoiceTranscriptRequest,
    VoiceTTSRequest,
)
from app.services.voice_service import (
    process_voice,
    process_voice_transcript,
    start_voice_session,
)
from app.services.voice.streaming.streaming_server import synthesize_speech, voice_stream

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


@router.post("/tts")
async def voice_tts_endpoint(request: VoiceTTSRequest) -> dict[str, str | None]:
    return {"audio_base64": await synthesize_speech(request.text)}


@router.websocket("/stream")
async def voice_stream_endpoint(
    websocket: WebSocket,
    session_id: str = "default",
    student_id: str = "ST001",
) -> None:
    await voice_stream(websocket, session_id=session_id, student_id=student_id)
