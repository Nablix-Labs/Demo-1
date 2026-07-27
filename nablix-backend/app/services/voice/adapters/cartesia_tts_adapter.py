import os
import sys
import time
import logging
from collections.abc import AsyncIterator

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import TTSAdapter, SpeechResult, register_tts_adapter
import config as voice_config

logger = logging.getLogger("cartesia_tts")

# Cartesia TTS REST endpoint.
# Docs: https://docs.cartesia.ai/api-reference/tts/bytes
CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"

# API version header required by Cartesia.
CARTESIA_API_VERSION = "2026-03-01"

# Reuse one async HTTP client so the TLS connection stays warm.
_cartesia_http_client: httpx.AsyncClient | None = None


def _get_client(api_key: str) -> httpx.AsyncClient:
    """Return a shared httpx client, creating it on first use."""
    global _cartesia_http_client
    if _cartesia_http_client is None:
        _cartesia_http_client = httpx.AsyncClient(
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Cartesia-Version": CARTESIA_API_VERSION,
            },
        )
    return _cartesia_http_client


# Curated Cartesia voice presets for the math tutor.
# Each entry maps a short label to a Cartesia voice UUID.
# Browse all voices at https://play.cartesia.ai/voices
CARTESIA_VOICES: dict[str, str] = {
    "Skylar - Friendly Guide": "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4",
    "Teacher Lady":            "573e3144-a684-4e72-ac2b-9b2063a50b53",
    "Tutorial Man":            "bd9120b6-7761-47a6-a446-77ca49132781",
    "Friendly Sidekick":       "e00d0e4c-a5c8-443f-a8a3-473eb9a62355",
    "Helpful Woman":           "156fb8d2-335b-4950-9cb3-a2d33befec77",
    "Calm Lady":               "00a77add-48d5-4ef6-8157-71e5437b282d",
    "Sweet Lady":              "e3827ec5-697a-4b7c-9704-1a23041bbc51",
    "Reading Lady":            "15a9cd88-84b0-4a8b-95f2-5d583b54c72e",
}


class CartesiaTTSAdapter(TTSAdapter):
    """Cartesia Sonic TTS adapter.

    Uses the REST API (POST /tts/bytes) with httpx.
    Cartesia Sonic claims ~40-90ms TTFA, making it the
    fastest commercial TTS as of mid-2026.

    Docs: https://docs.cartesia.ai/api-reference/tts/bytes
    Voice library: https://play.cartesia.ai/voices
    """

    # Default voice: "Skylar - Friendly Guide" -- warm, approachable.
    # Browse voices at https://play.cartesia.ai/voices
    # You can swap this for any voice ID from their library.
    DEFAULT_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
    DEFAULT_MODEL = "sonic-3.5"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("CARTESIA_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Cartesia API key not found. "
                "Set CARTESIA_API_KEY in your .env file."
            )

    def _build_request_body(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> dict:
        """Build the JSON request body for Cartesia's API."""
        voice_id = voice or self.DEFAULT_VOICE_ID

        # Build output_format based on requested audio format.
        if audio_format == "mp3":
            output_format = {
                "container": "mp3",
                "sample_rate": 24000,
                "bit_rate": 128000,
            }
        elif audio_format == "wav":
            output_format = {
                "container": "wav",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            }
        else:
            # Default to raw PCM if format is unknown.
            output_format = {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            }

        return {
            "model_id": self.DEFAULT_MODEL,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": voice_id,
            },
            "language": "en",
            "output_format": output_format,
        }

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        """Generate full audio in one shot (non-streaming)."""
        start = time.time()

        body = self._build_request_body(text, voice, audio_format)
        client = _get_client(self.api_key)

        response = await client.post(CARTESIA_TTS_URL, json=body)

        if response.status_code != 200:
            elapsed_ms = int((time.time() - start) * 1000)
            raise RuntimeError(
                f"Cartesia TTS failed: status={response.status_code} "
                f"body={response.text[:200]}"
            )

        audio_bytes = response.content
        elapsed_ms = int((time.time() - start) * 1000)

        logger.info(
            f"Cartesia TTS: {len(text)} chars -> {len(audio_bytes)} bytes "
            f"in {elapsed_ms}ms"
        )

        # Rough duration estimate.
        if audio_format == "mp3":
            estimated_duration = len(audio_bytes) / 16000
        elif audio_format == "wav":
            estimated_duration = len(audio_bytes) / 48000
        else:
            estimated_duration = len(audio_bytes) / 48000

        return SpeechResult(
            audio_data=audio_bytes,
            audio_format=audio_format,
            duration_seconds=round(estimated_duration, 1),
            latency_ms=elapsed_ms,
            provider=f"cartesia_{self.DEFAULT_MODEL}",
        )

    async def generate_speech_stream(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
        chunk_size: int = 4096,
    ) -> AsyncIterator[bytes]:
        """Yield audio chunks as Cartesia generates them.

        Uses httpx streaming to read the response body in chunks
        as it arrives, rather than waiting for the full response.
        """
        body = self._build_request_body(text, voice, audio_format)

        # For streaming, we need a separate request (can't use the
        # shared client's .post() because we need stream=True).
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Cartesia-Version": CARTESIA_API_VERSION,
            },
        ) as stream_client:
            async with stream_client.stream(
                "POST", CARTESIA_TTS_URL, json=body
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise RuntimeError(
                        f"Cartesia TTS stream failed: "
                        f"status={response.status_code} "
                        f"body={error_body[:200]}"
                    )
                async for chunk in response.aiter_bytes(chunk_size):
                    yield chunk

    async def is_available(self) -> bool:
        """Check if the adapter can reach Cartesia's API."""
        try:
            client = _get_client(self.api_key)
            body = self._build_request_body(".", audio_format="mp3")
            response = await client.post(CARTESIA_TTS_URL, json=body)
            return response.status_code == 200
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return f"cartesia_{self.DEFAULT_MODEL}"


# Only register if the API key is available.
if os.getenv("CARTESIA_API_KEY"):
    register_tts_adapter("cartesia", CartesiaTTSAdapter)
