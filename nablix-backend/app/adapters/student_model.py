"""Student-model adapter.

The student model has two responsibilities: estimate the learner state for the
current turn and accept events that should update that state. Both paths share
the same typed result so the tutor pipeline can continue without caring whether
the source is mock data or a live service.
"""

from typing import NoReturn

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, StudentModelEvent, StudentModelResult


class StudentModelServiceAdapter:
    """Reads and updates student state through mock data or a service URL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def assess(self, context: AdapterContext) -> StudentModelResult:
        """Service-facing method for reading the current learner-state estimate."""

        return await self.call(context)

    async def call(self, request: AdapterContext) -> StudentModelResult:
        """Return a mock state snapshot or call the live student-model service."""

        if self._settings.use_mock_student_model:
            return self._mock_response()

        payload: JsonObject = request.model_dump(mode="json", exclude={"canvas_regions"})
        try:
            response = await post_json(
                "student_model",
                self._settings.student_model_url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def parse_response(self, response: dict[str, object]) -> StudentModelResult:
        try:
            return StudentModelResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid response body={response}: {error}",
            ) from error

    def handle_error(self, error: AdapterError) -> NoReturn:
        raise error

    async def update_from_event(self, event: StudentModelEvent) -> StudentModelResult:
        """Persist a tutor/student event and return the updated learner state."""

        if self._settings.use_mock_student_model:
            return self._mock_response()

        payload: JsonObject = event.model_dump(mode="json")
        try:
            response = await post_json(
                "student_model",
                self._settings.student_model_url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def _mock_response(self) -> StudentModelResult:
        """Return the stable development snapshot used by tutor-route tests."""

        return StudentModelResult(
            student_state="NEEDS_GUIDANCE",
            confidence=0.82,
            mastery_level="DEVELOPING",
            recommended_support="STEP_BY_STEP_HINT",
        )


class MockStudentModelAdapter(StudentModelServiceAdapter):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(Settings(use_mock_student_model=True))
