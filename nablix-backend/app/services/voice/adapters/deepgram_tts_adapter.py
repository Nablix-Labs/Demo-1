import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

# Deepgram TTS REST endpoint.
# Docs: https://developers.deepgram.com/docs/text-to-speech
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"

# Reuse one async HTTP client so the TLS connection stays warm after
# the first call (same pattern we use for the main backend client).
_dg_http_client: httpx.AsyncClient | None = None


def _get_client(api_key: str) -> httpx.AsyncClient:
    """Return a shared httpx client, creating it on first use."""
    global _dg_http_client
    if _dg_http_client is None:
        _dg_http_client = httpx.AsyncClient(
            timeout=10.0,
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
            },
        )
    return _dg_http_client


class DeepgramTTSAdapter(TTSAdapter):
    """Deepgram Aura TTS adapter.

    Uses the REST API (POST /v1/speak) with httpx.  No extra SDK
    dependency needed -- the endpoint accepts JSON and returns raw
    audio bytes.

    Typical latency: 200-400ms (vs 2-3 seconds with OpenAI TTS).
    """

    # Default Deepgram voice if none is specified.
    # Full list: https://developers.deepgram.com/docs/tts-models
    DEFAULT_VOICE = "aura-2-thalia-en"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or voice_config.DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError(
                "Deepgram API key not found. "
                "Set DEEPGRAM_API_KEY in your .env file."
            )

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        start = time.time()

        # Pick the model name.  If the caller passes a full Deepgram
        # model name (like "aura-2-thalia-en") use it directly.
        # Otherwise fall back to the default.
        model = voice or self.DEFAULT_VOICE

        # Build the query string.
        # encoding/container tell Deepgram what audio format to return.
        params = {"model": model}
        if audio_format == "mp3":
            params["encoding"] = "mp3"
        elif audio_format == "wav":
            params["encoding"] = "linear16"
            params["container"] = "wav"

        client = _get_client(self.api_key)

        response = await client.post(
            DEEPGRAM_TTS_URL,
            params=params,
            json={"text": text},
        )

        if response.status_code != 200:
            elapsed_ms = int((time.time() - start) * 1000)
            raise RuntimeError(
                f"Deepgram TTS failed: status={response.status_code} "
                f"body={response.text[:200]}"
            )

        audio_bytes = response.content
        elapsed_ms = int((time.time() - start) * 1000)

        # Rough duration estimate based on byte size.
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
            provider="deepgram_aura2",
        )

    async def is_available(self) -> bool:
        try:
            client = _get_client(self.api_key)
            response = await client.post(
                DEEPGRAM_TTS_URL,
                params={"model": self.DEFAULT_VOICE},
                json={"text": "."},
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "deepgram_aura2"


if voice_config.DEEPGRAM_API_KEY:
    register_tts_adapter("deepgram", DeepgramTTSAdapter)
