from app.adapters.provider import AdapterSet, get_adapters
from app.models.adapters import VoiceResult
from app.models.interaction import InteractionRequest, InteractionResponse
from app.models.session import SessionRecord
from app.models.voice import (
    VoiceRequest,
    VoiceResponse,
    VoiceSessionStartRequest,
    VoiceSessionStartResponse,
    VoiceTranscriptRequest,
)
from app.services.interaction_service import process_interaction
from app.services.session_service import _get_owned_session, start_voice_stream


def _mock_voice_session_token(session_id: str) -> str:
    """Return the placeholder token used until Realtime sessions are live."""

    return f"mock_voice_token_{session_id}"


async def process_voice(request: VoiceRequest) -> VoiceResponse:
    """Transcribe one audio reference through the voice adapter."""

    adapters: AdapterSet = get_adapters()
    result: VoiceResult = await adapters.voice.transcribe(request.audio_reference)

    return VoiceResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        transcript=result.transcript,
        confidence=result.confidence,
        language=result.language,
    )


async def start_voice_session(
    request: VoiceSessionStartRequest,
) -> VoiceSessionStartResponse:
    """Open a mock voice stream for an existing tutoring session."""

    session: SessionRecord = start_voice_stream(request.session_id, request.student_id)
    return VoiceSessionStartResponse(
        session_id=session.session_id,
        student_id=session.student_id,
        stream_active=session.voice_state.stream_active,
        current_turn=session.voice_state.current_turn,
        voice_session_token=_mock_voice_session_token(session.session_id),
        fallback_active=session.voice_state.fallback_active,
    )


async def process_voice_transcript(
    request: VoiceTranscriptRequest,
    access_token: str,
) -> InteractionResponse:
    """Route one voice transcript through the same interaction flow as text."""

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    interaction_request: InteractionRequest = InteractionRequest(
        session_id=request.session_id,
        student_id=request.student_id,
        interaction_type="ANSWER_SUBMISSION",
        input_source="VOICE",
        text_input=None,
        voice_transcript=request.transcript,
        transcript_confidence=request.confidence,
        canvas_snapshot_id=None,
        current_phase=session.current_phase,
        concept_id=session.concept_id,
        question_id=session.question_id,
        hint_count=session.hint_count,
        timestamp=request.timestamp.isoformat(),
    )
    return await process_interaction(interaction_request, access_token)
