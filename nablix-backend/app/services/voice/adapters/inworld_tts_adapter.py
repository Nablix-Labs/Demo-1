import os
import sys
import time
import base64
import logging
from collections.abc import AsyncIterator

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

logger = logging.getLogger("inworld_tts")

# Inworld TTS REST endpoints.
# Docs: https://docs.inworld.ai/api-reference/ttsAPI/texttospeech/synthesize-speech
INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"
INWORLD_TTS_STREAM_URL = "https://api.inworld.ai/tts/v1/voice:stream"

# Reuse one async HTTP client so the TLS connection stays warm.
_inworld_http_client: httpx.AsyncClient | None = None


def _get_client(api_key: str) -> httpx.AsyncClient:
    """Return a shared httpx client, creating it on first use."""
    global _inworld_http_client
    if _inworld_http_client is None:
        _inworld_http_client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "Authorization": f"Basic {api_key}",
                "Content-Type": "application/json",
            },
        )
    return _inworld_http_client


class InworldTTSAdapter(TTSAdapter):
    """Inworld Realtime TTS adapter.

    Uses the REST API (POST /tts/v1/voice) with httpx.
    Inworld TTS 1.5 Mini claims ~100ms TTFA at $5/M chars,
    making it one of the best quality-per-dollar options.

    Docs: https://docs.inworld.ai/api-reference/ttsAPI/texttospeech/synthesize-speech
    Auth: Basic auth with base64 API key from Inworld Portal.
    Response: JSON with base64-encoded audioContent field.
    """

    # Default voice. Browse voices at https://platform.inworld.ai/tts-playground
    DEFAULT_VOICE = "Ashley"
    DEFAULT_MODEL = "inworld-tts-1.5-mini"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("INWORLD_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Inworld API key not found. "
                "Set INWORLD_API_KEY in your .env file. "
                "Get one from https://platform.inworld.ai/api-keys"
            )

    def _build_request_body(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> dict:
        """Build the JSON request body for Inworld's API."""
        voice_id = voice or self.DEFAULT_VOICE

        # Map our audio_format to Inworld's audioEncoding.
        if audio_format == "mp3":
            encoding = "MP3"
        elif audio_format == "wav":
            encoding = "WAV"
        else:
            encoding = "MP3"

        return {
            "text": text,
            "voiceId": voice_id,
            "modelId": self.DEFAULT_MODEL,
            "language": "en-US",
            "audioConfig": {
                "audioEncoding": encoding,
                "sampleRateHertz": 24000,
            },
            "deliveryMode": "BALANCED",
            "applyTextNormalization": "ON",
        }

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        """Generate full audio in one shot (non-streaming).

        Inworld's sync endpoint returns JSON with a base64-encoded
        audioContent field. We decode that to get the raw audio bytes.
        """
        start = time.time()

        body = self._build_request_body(text, voice, audio_format)
        client = _get_client(self.api_key)

        response = await client.post(INWORLD_TTS_URL, json=body)

        if response.status_code != 200:
            elapsed_ms = int((time.time() - start) * 1000)
            raise RuntimeError(
                f"Inworld TTS failed: status={response.status_code} "
                f"body={response.text[:200]}"
            )

        data = response.json()
        audio_b64 = data.get("audioContent", "")
        audio_bytes = base64.b64decode(audio_b64)

        elapsed_ms = int((time.time() - start) * 1000)

        logger.info(
            f"Inworld TTS: {len(text)} chars -> {len(audio_bytes)} bytes "
            f"in {elapsed_ms}ms"
        )

        # Rough duration estimate.
        if audio_format == "mp3":
            estimated_duration = len(audio_bytes) / 16000
        elif audio_format == "wav":
            estimated_duration = len(audio_bytes) / 48000
        else:
            estimated_duration = len(audio_bytes) / 16000

        return SpeechResult(
            audio_data=audio_bytes,
            audio_format=audio_format,
            duration_seconds=round(estimated_duration, 1),
            latency_ms=elapsed_ms,
            provider=f"inworld_{self.DEFAULT_MODEL}",
        )

    async def generate_speech_stream(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
        chunk_size: int = 4096,
    ) -> AsyncIterator[bytes]:
        """Yield audio chunks from Inworld's streaming endpoint.

        The streaming endpoint (POST /tts/v1/voice:stream) returns
        newline-delimited JSON (NDJSON), where each line contains
        a base64-encoded audio chunk. We decode each chunk and yield it.
        """
        voice_id = voice or self.DEFAULT_VOICE

        if audio_format == "mp3":
            encoding = "MP3"
        elif audio_format == "wav":
            encoding = "WAV"
        else:
            encoding = "MP3"

        body = {
            "text": text,
            "voiceId": voice_id,
            "modelId": self.DEFAULT_MODEL,
            "language": "en-US",
            "audioConfig": {
                "audioEncoding": encoding,
                "sampleRateHertz": 24000,
            },
            "deliveryMode": "BALANCED",
            "applyTextNormalization": "ON",
        }

        import json

        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "Authorization": f"Basic {self.api_key}",
                "Content-Type": "application/json",
            },
        ) as stream_client:
            async with stream_client.stream(
                "POST", INWORLD_TTS_STREAM_URL, json=body
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise RuntimeError(
                        f"Inworld TTS stream failed: "
                        f"status={response.status_code} "
                        f"body={error_body[:200]}"
                    )
                # NDJSON: each line is a JSON object like:
                # {"result": {"audioContent": "<base64>", "usage": {...}}}
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk_data = json.loads(line)
                        # audioContent is nested inside "result"
                        result = chunk_data.get("result", {})
                        audio_b64 = result.get("audioContent", "")
                        if audio_b64:
                            yield base64.b64decode(audio_b64)
                    except json.JSONDecodeError:
                        logger.warning(f"Skipping invalid NDJSON line")
                        continue

    async def is_available(self) -> bool:
        """Check if the adapter can reach Inworld's API."""
        try:
            client = _get_client(self.api_key)
            body = self._build_request_body(".", audio_format="mp3")
            response = await client.post(INWORLD_TTS_URL, json=body)
            return response.status_code == 200
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return f"inworld_{self.DEFAULT_MODEL}"


# Only register if the API key is available.
if os.getenv("INWORLD_API_KEY"):
    register_tts_adapter("inworld", InworldTTSAdapter)
