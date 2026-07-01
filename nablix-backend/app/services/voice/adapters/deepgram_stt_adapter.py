import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from adapter import STTAdapter, TranscriptionResult, register_stt_adapter
import config as voice_config

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"

class DeepgramSTTAdapter(STTAdapter):

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or voice_config.DEEPGRAM_API_KEY
        if not self.api_key:
            raise ValueError(
                "Deepgram API key not found. "
                "Sign up at console.deepgram.com and set DEEPGRAM_API_KEY in .env"
            )
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def transcribe_audio(
        self,
        audio_data: bytes | str,
        language: str = "en",
        audio_format: str = "wav",
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        start = time.time()

        if isinstance(audio_data, str) and os.path.isfile(audio_data):
            with open(audio_data, "rb") as f:
                audio_bytes = f.read()
        elif isinstance(audio_data, bytes):
            audio_bytes = audio_data
        else:
            raise ValueError(
                f"audio_data must be a file path or bytes, got {type(audio_data)}"
            )

        params = {
            "model": "nova-3",
            "language": language,
            "smart_format": "true",
            "punctuate": "true",
        }

        mime_types = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "webm": "audio/webm",
            "ogg": "audio/ogg",
            "flac": "audio/flac",
            "m4a": "audio/mp4",
        }
        content_type = mime_types.get(audio_format, f"audio/{audio_format}")

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": content_type,
        }

        try:
            response = await self.http_client.post(
                DEEPGRAM_API_URL,
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Deepgram API error ({e.response.status_code}): {e.response.text}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Deepgram STT request failed: {e}") from e

        elapsed_ms = int((time.time() - start) * 1000)

        try:
            channels = result["results"]["channels"]
            if not channels or not channels[0].get("alternatives"):
                return TranscriptionResult(
                    transcript="",
                    confidence=0.0,
                    language=language,
                    latency_ms=elapsed_ms,
                    provider="deepgram_nova3",
                )

            best_alt = channels[0]["alternatives"][0]
            transcript = best_alt.get("transcript", "").strip()
            confidence = best_alt.get("confidence", 0.0)

            return TranscriptionResult(
                transcript=transcript,
                confidence=round(confidence, 4),
                language=language,
                latency_ms=elapsed_ms,
                provider="deepgram_nova3",
            )

        except (KeyError, IndexError) as e:
            raise RuntimeError(
                f"Unexpected Deepgram response format: {e}\n"
                f"Response: {result}"
            ) from e

    async def is_available(self) -> bool:
        try:
            response = await self.http_client.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {self.api_key}"},
                timeout=5.0,
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "deepgram_nova3"

if voice_config.DEEPGRAM_API_KEY:
    register_stt_adapter("deepgram", DeepgramSTTAdapter)
