import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

from openai import OpenAI

from adapter import STTAdapter, TranscriptionResult, register_stt_adapter
import config as voice_config

class OpenAISTTAdapter(STTAdapter):

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or voice_config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY in your .env file."
            )
        self.client = OpenAI(api_key=self.api_key)
        self.model = "whisper-1"

    async def transcribe_audio(
        self,
        audio_data: bytes | str,
        language: str = "en",
        audio_format: str = "wav",
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        start = time.time()

        try:
            if isinstance(audio_data, str) and os.path.isfile(audio_data):
                with open(audio_data, "rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        language=language,
                        response_format="verbose_json",
                    )
            elif isinstance(audio_data, bytes):
                suffix = f".{audio_format}"
                tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                try:
                    tmp.write(audio_data)
                    tmp.close()
                    with open(tmp.name, "rb") as audio_file:
                        response = self.client.audio.transcriptions.create(
                            model=self.model,
                            file=audio_file,
                            language=language,
                            response_format="verbose_json",
                        )
                finally:
                    os.unlink(tmp.name)
            else:
                raise ValueError(
                    f"audio_data must be a file path or bytes, got {type(audio_data)}"
                )

            elapsed_ms = int((time.time() - start) * 1000)

            transcript = response.text.strip() if response.text else ""

            confidence = self._extract_confidence(response)

            return TranscriptionResult(
                transcript=transcript,
                confidence=confidence,
                language=language,
                latency_ms=elapsed_ms,
                provider="openai_whisper",
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            raise RuntimeError(f"OpenAI STT failed: {e}") from e

    def _extract_confidence(self, response) -> float:
        try:
            if hasattr(response, "segments") and response.segments:
                logprobs = [s.get("avg_logprob", -0.5) if isinstance(s, dict)
                           else getattr(s, "avg_logprob", -0.5)
                           for s in response.segments]
                avg_logprob = sum(logprobs) / len(logprobs)
                confidence = max(0.0, min(1.0, 1.0 + avg_logprob))
                return round(confidence, 4)
        except Exception:
            pass

        return 0.85

    async def is_available(self) -> bool:
        try:
            self.client.models.list()
            return True
        except Exception:
            return False

    def get_provider_name(self) -> str:
        return "openai_whisper"

register_stt_adapter("openai", OpenAISTTAdapter)
