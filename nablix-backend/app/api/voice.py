from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import JSONResponse

from app.api.auth import AccessToken
from app.models.interaction import InteractionResponse, StaleTurnResponse
from app.models.teach_back_realtime import TeachBackRealtimeContext, TeachBackRealtimeResult, TeachBackRealtimeSession, TeachBackRealtimeStart
from app.ai_engine.teach_back import load_teach_back_config
from app.services.teach_back_realtime import realtime_teach_back_context, start_realtime_teach_back
from app.services.interaction_service import process_realtime_teach_back
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
        return {
            "audio_base64": await synthesize_speech(
                request.text,
                provider=request.provider,
                voice=request.voice,
            )
        }
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
    tts_provider: str | None = None,
    tts_voice: str | None = None,
) -> None:
    # Frontends have sent both ?session= and ?session_id= at different points;
    # accept either so a client/server version skew can't silently drop the ID.
    await voice_stream(
        websocket,
        session=session_id or session,
        student_id=student_id,
        tts_provider=tts_provider,
        tts_voice=tts_voice,
    )


@router.get("/teach-back/options")
async def teach_back_voice_options() -> dict[str, bool]:
    return {"realtime_enabled": load_teach_back_config().realtime.enabled}


@router.post("/teach-back/session", response_model=TeachBackRealtimeSession)
async def teach_back_realtime_session(
    request: TeachBackRealtimeStart, access_token: AccessToken,
) -> TeachBackRealtimeSession:
    return await start_realtime_teach_back(request, access_token)


@router.post("/teach-back/context", response_model=TeachBackRealtimeContext)
async def teach_back_realtime_context(
    request: TeachBackRealtimeStart, access_token: AccessToken,
) -> TeachBackRealtimeContext:
    return await realtime_teach_back_context(request, access_token)


@router.post("/teach-back/result", response_model=InteractionResponse)
async def teach_back_realtime_result(
    request: TeachBackRealtimeResult, access_token: AccessToken,
) -> InteractionResponse | JSONResponse:
    if not load_teach_back_config().realtime.enabled:
        raise HTTPException(status_code=409, detail="Realtime Teach-Back is disabled.")
    response = await process_realtime_teach_back(request, access_token)
    if isinstance(response, StaleTurnResponse):
        return JSONResponse(status_code=409, content=response.model_dump())
    return response
