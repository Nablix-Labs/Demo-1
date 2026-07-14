"""In-process student-model adapter."""

from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, StudentModelEvent, StudentModelResult


class StudentModelServiceAdapter:
    """Provides the in-process learner-state snapshot."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def assess(self, context: AdapterContext) -> StudentModelResult:
        """Service-facing method for reading the current learner-state estimate."""

        return await self.call(context)

    async def call(self, request: AdapterContext) -> StudentModelResult:
        """Return the local state snapshot without a network hop."""

        return self._local_response()

    def parse_response(self, response: dict[str, object]) -> StudentModelResult:
        try:
            return StudentModelResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid response body={response}: {error}",
            ) from error

    async def update_from_event(self, event: StudentModelEvent) -> StudentModelResult:
        """Return the local state snapshot after an event."""

        return self._local_response()

    def _local_response(self) -> StudentModelResult:
        """Return the stable in-process learner-state snapshot."""

        return StudentModelResult(
            student_state="NEEDS_GUIDANCE",
            confidence=0.82,
            mastery_level="DEVELOPING",
            recommended_support="STEP_BY_STEP_HINT",
        )


class MockStudentModelAdapter(StudentModelServiceAdapter):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(Settings())
