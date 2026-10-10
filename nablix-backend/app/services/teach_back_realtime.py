from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.adapters.http_utils import post_json
from app.ai_engine.teach_back import load_teach_back_config
from app.core.config import get_settings
from app.models.teach_back_realtime import TeachBackRealtimeSession, TeachBackRealtimeStart
from app.services.interaction_service import recover_session_for_read
from app.services.session_service import require_learning_active, require_teach_back_recovered


class RealtimeClientSecret(BaseModel):
    value: str = Field(min_length=1)


def build_realtime_voice_session() -> dict[str, object]:
    """Session that only transcribes the student and speaks text it is given; it never replies on its own."""
    config = load_teach_back_config().realtime
    audio_input: dict[str, object] = {
        "transcription": {"model": config.transcription_model, "language": config.transcription_language,
                          "prompt": config.transcription_prompt},
        "turn_detection": {**config.turn_detection, "create_response": False, "interrupt_response": False},
    }
    if config.noise_reduction is not None:
        audio_input["noise_reduction"] = {"type": config.noise_reduction}
    return {
        "type": "realtime", "model": config.model, "instructions": config.speaker_instructions,
        "output_modalities": ["audio"], "include": ["item.input_audio_transcription.logprobs"],
        "audio": {"input": audio_input, "output": {"voice": config.voice}},
    }


async def start_realtime_teach_back(
    request: TeachBackRealtimeStart, access_token: str,
) -> TeachBackRealtimeSession:
    config = load_teach_back_config().realtime
    if not config.enabled:
        raise HTTPException(status_code=409, detail="Realtime Teach-Back is disabled in teach_back_tutor.yaml.")
    session = await recover_session_for_read(request.session_id, request.student_id, access_token)
    require_learning_active(session)
    require_teach_back_recovered(session)
    content = session.teach_back_content
    if session.current_phase != "TEACH_BACK" or content is None:
        raise HTTPException(status_code=409, detail="Realtime voice is only available during Teach-Back.")
    if content.state.current_micro_skill_id is None:
        raise HTTPException(status_code=409, detail="Teach-Back has no unfinished target.")
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="Configure NABLIX_OPENAI_API_KEY before starting Realtime Teach-Back.")
    body = await post_json(
        "teach_back_realtime", config.client_secret_url,
        {"expires_after": {"anchor": "created_at", "seconds": config.token_lifetime_seconds},
         "session": build_realtime_voice_session()},
        {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        settings.openai_request_timeout_seconds, settings.adapter_request_retry_count,
    )
    secret = RealtimeClientSecret.model_validate(body)
    return TeachBackRealtimeSession(client_secret=secret.value, calls_url=config.calls_url,
                                    response_timeout_seconds=config.response_timeout_seconds,
                                    request_retry_count=settings.adapter_request_retry_count,
                                    speaker_instructions=config.speaker_instructions,
                                    filler_words=config.filler_words)
