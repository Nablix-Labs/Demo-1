from fastapi import APIRouter, HTTPException, WebSocket

from app.api.auth import AccessToken
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
    access_token: AccessToken,
) -> InteractionResponse:
    return await process_voice_transcript(request, access_token)


@router.post("/tts")
async def voice_tts_endpoint(request: VoiceTTSRequest) -> dict[str, str | None]:
    try:
        return {"audio_base64": await synthesize_speech(request.text)}
    except RuntimeError as error:
        # Explicit failure so the frontend can fall back to browser speech.
        raise HTTPException(
            status_code=502,
            detail="Text-to-speech is unavailable right now.",
        ) from error


@router.websocket("/stream")
async def voice_stream_endpoint(
    websocket: WebSocket,
    session: str = "default",
    session_id: str | None = None,
    student_id: str = "ST001",
) -> None:
    # Frontends have sent both ?session= and ?session_id= at different points;
    # accept either so a client/server version skew can't silently drop the ID.
    await voice_stream(websocket, session=session_id or session, student_id=student_id)
