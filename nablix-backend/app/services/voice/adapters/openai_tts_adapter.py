import os
import sys
import time
import logging
from collections.abc import AsyncIterator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

logger = logging.getLogger("openai_tts")


class OpenAITTSAdapter(TTSAdapter):
    """OpenAI TTS adapter using the async client.

    Supports two modes:
      1. generate_speech()        - waits for full audio (original)
      2. generate_speech_stream() - yields audio chunks as OpenAI
                                    generates them (streaming)

    Streaming lets the frontend start playing audio within 300-500ms
    instead of waiting 2-3 seconds for the full file.
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
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.default_voice = default_voice

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        """Generate full audio in one shot (non-streaming)."""
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

    async def generate_speech_stream(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
        chunk_size: int = 4096,
    ) -> AsyncIterator[bytes]:
        """Yield audio chunks as OpenAI generates them.

        Instead of waiting for the entire audio file (2-3 seconds),
        this uses OpenAI's streaming response.  The first chunk
        typically arrives in 300-500ms, allowing the frontend to
        start playback immediately.

        Usage:
            adapter = get_tts_adapter("openai")
            async for chunk in adapter.generate_speech_stream(text):
                # send chunk to frontend via WebSocket
        """
        selected_voice = voice or self.default_voice

        openai_format = "mp3" if audio_format == "mp3" else audio_format

        async with self.client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=selected_voice,
            input=text,
            response_format=openai_format,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=chunk_size):
                yield chunk

    async def is_available(self) -> bool:
        return bool(self.api_key)

    def get_provider_name(self) -> str:
        return f"openai_{self.model}"


register_tts_adapter("openai", OpenAITTSAdapter)
