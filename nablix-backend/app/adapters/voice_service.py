"""Voice-service adapter.

The voice adapter accepts an audio reference owned by the API layer and returns
a normalized transcript DTO. It does not decide what the transcript means; the
interaction service sends that text through the tutor pipeline.
"""

from typing import NoReturn

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import VoiceResult


class VoiceServiceAdapterClient:
    """Transcribes audio through mock data or a live voice service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def transcribe(self, audio_reference: str) -> VoiceResult:
        """Service-facing method used by voice routes."""

        return await self.call(audio_reference)

    async def call(self, request: str) -> VoiceResult:
        """Return a mock transcript or call the configured voice service."""

        if self._settings.use_mock_voice:
            return self._mock_response(request)

        payload: JsonObject = {"audio_reference": request}
        try:
            response = await post_json(
                "voice_service",
                self._settings.voice_service_url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def parse_response(self, response: dict[str, object]) -> VoiceResult:
        try:
            return VoiceResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "voice_service",
                f"invalid response body={response}: {error}",
            ) from error

    def handle_error(self, error: AdapterError) -> NoReturn:
        raise error

    def _mock_response(self, request: str) -> VoiceResult:
        """Return a stable transcript shaped like speech-recognition output."""

        return VoiceResult(
            transcript="I got twelve, but I think I made a mistake in the second step.",
            confidence=0.94,
            language="en",
        )


class MockVoiceServiceAdapter(VoiceServiceAdapterClient):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(Settings(use_mock_voice=True))
