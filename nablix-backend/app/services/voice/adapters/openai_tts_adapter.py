import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from openai import AsyncOpenAI

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

class OpenAITTSAdapter(TTSAdapter):
    """OpenAI TTS adapter using the async client.

    The original code used the synchronous OpenAI client inside an
    async method, which blocks the entire event loop while waiting
    for the API response (typically 1-3 seconds).  Switching to
    AsyncOpenAI lets other tasks (like sending WebSocket messages)
    run while TTS generates.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "tts-1",
        default_voice: str = "nova",
    ):
        self.api_key = api_key or voice_config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY in your .env file."
            )
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.default_voice = default_voice

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        start = time.time()
        selected_voice = voice or self.default_voice

        try:
            openai_format = audio_format
            if audio_format == "wav":
                openai_format = "wav"
            elif audio_format == "mp3":
                openai_format = "mp3"

            response = await self.client.audio.speech.create(
                model=self.model,
                voice=selected_voice,
                input=text,
                response_format=openai_format,
            )

            audio_bytes = response.content

            elapsed_ms = int((time.time() - start) * 1000)

            if audio_format == "mp3":
                estimated_duration = len(audio_bytes) / 16000
            elif audio_format == "wav":
                estimated_duration = len(audio_bytes) / 32000
            else:
                estimated_duration = len(audio_bytes) / 16000

            return SpeechResult(
                audio_data=audio_bytes,
                audio_format=audio_format,
                duration_seconds=round(estimated_duration, 1),
                latency_ms=elapsed_ms,
                provider=f"openai_{self.model}",
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            raise RuntimeError(f"OpenAI TTS failed: {e}") from e

    def get_provider_name(self) -> str:
        return f"openai_{self.model}"

register_tts_adapter("openai", OpenAITTSAdapter)
