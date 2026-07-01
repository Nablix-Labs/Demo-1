import asyncio
import time

from adapter import (
    STTAdapter,
    TTSAdapter,
    TranscriptionResult,
    SpeechResult,
    register_stt_adapter,
    register_tts_adapter,
)

MOCK_TRANSCRIPTIONS = {
    "correct_answer": {
        "transcript": "x equals five",
        "confidence": 0.95,
    },
    "wrong_answer": {
        "transcript": "x equals six",
        "confidence": 0.92,
    },
    "hint_request": {
        "transcript": "can I get a hint",
        "confidence": 0.97,
    },
    "confused": {
        "transcript": "I don't understand",
        "confidence": 0.88,
    },
    "math_fraction": {
        "transcript": "five over six",
        "confidence": 0.90,
    },
    "math_expression": {
        "transcript": "x times five plus y",
        "confidence": 0.85,
    },
    "low_confidence": {
        "transcript": "uhm maybe seven",
        "confidence": 0.35,
    },
    "silence": {
        "transcript": "",
        "confidence": 0.0,
    },
}

DEFAULT_MOCK_TRANSCRIPTION = {
    "transcript": "x equals five",
    "confidence": 0.95,
}

class MockSTTAdapter(STTAdapter):

    async def transcribe_audio(
        self,
        audio_data: bytes | str,
        language: str = "en",
        audio_format: str = "wav",
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        start = time.time()

        await asyncio.sleep(0.1)

        key = str(audio_data)
        mock = MOCK_TRANSCRIPTIONS.get(key, DEFAULT_MOCK_TRANSCRIPTION)

        elapsed_ms = int((time.time() - start) * 1000)

        return TranscriptionResult(
            transcript=mock["transcript"],
            confidence=mock["confidence"],
            language=language,
            latency_ms=elapsed_ms,
            provider="mock_stt",
        )

    async def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "mock_stt"

MOCK_AUDIO_RESPONSES = {
}

class MockTTSAdapter(TTSAdapter):

    async def generate_speech(
        self,
        text: str,
        voice: str | None = None,
        audio_format: str = "mp3",
    ) -> SpeechResult:
        start = time.time()

        await asyncio.sleep(0.05)

        word_count = len(text.split())
        estimated_duration = word_count / 2.5

        elapsed_ms = int((time.time() - start) * 1000)

        return SpeechResult(
            audio_data=f"mock_audio://{text}",
            audio_format=audio_format,
            duration_seconds=round(estimated_duration, 1),
            latency_ms=elapsed_ms,
            provider="mock_tts",
        )

    async def is_available(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "mock_tts"

register_stt_adapter("mock", MockSTTAdapter)
register_tts_adapter("mock", MockTTSAdapter)
