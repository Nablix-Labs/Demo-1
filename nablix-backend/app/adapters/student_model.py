"""Student Model adapter backed by Saravanan's HTTP contract."""

import json

from pydantic import ValidationError

from app.adapters.http_utils import post_json
from app.core.config import Settings
from app.core.exceptions import (
    AdapterError,
    AdapterRequestRejected,
    JourneyVersionConflict,
)
from app.models.adapters import AdapterContext, StudentModelResult
from app.models.student_model_session import (
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)


class StudentModelServiceAdapter:
    """Reads local pre-turn state and persists evaluated events remotely."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def assess(self, context: AdapterContext) -> StudentModelResult:
        """Service-facing method for reading the current learner-state estimate."""

        return await self.call(context)

    async def call(self, request: AdapterContext) -> StudentModelResult:
        """Return neutral pre-turn state; the remote service accepts events only."""

        return self._local_response(request)

    def parse_response(self, response: dict[str, object]) -> StudentModelResult:
        try:
            return StudentModelResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid response body={response}: {error}",
            ) from error

    async def send_session_event(
        self,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        """Persist one Schema 3.0 journey event and return its full state."""

        if self._settings.use_mock_student_model:
            raise AdapterError(
                "student_model",
                "Schema 3.0 session events require NABLIX_USE_MOCK_STUDENT_MODEL=false",
            )
        if self._settings.student_model_url == "":
            raise AdapterError(
                "student_model",
                "NABLIX_STUDENT_MODEL_URL is required for Schema 3.0 session events",
            )
        try:
            response = await post_json(
                "student_model",
                f"{self._settings.student_model_url.rstrip('/')}/session/event",
                event.model_dump(exclude_none=True),
                {"Authorization": f"Bearer {access_token}"},
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
        except AdapterRequestRejected as error:
            if error.status_code != 409:
                raise
            try:
                conflict_body: object = json.loads(error.response_body)
            except json.JSONDecodeError:
                raise error
            if not isinstance(conflict_body, dict) or conflict_body.get(
                "error_code"
            ) != "JOURNEY_VERSION_CONFLICT":
                raise
            raise JourneyVersionConflict(conflict_body) from error
        try:
            parsed = StudentModelSessionEventResponse.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid Schema 3.0 response body={response}: {error}",
            ) from error
        if (
            parsed.request_id != event.request_id
            or parsed.journey_state.student_id != event.student_id
            or parsed.journey_state.topic_id != event.topic_id
        ):
            raise AdapterError(
                "student_model",
                (
                    "Schema 3.0 response identity mismatch "
                    f"request_id={parsed.request_id} "
                    f"student_id={parsed.journey_state.student_id} "
                    f"topic_id={parsed.journey_state.topic_id} body={response}"
                ),
            )
        if parsed.status.status_code == "JOURNEY_VERSION_CONFLICT":
            raise JourneyVersionConflict(response)
        if not parsed.status.success:
            raise AdapterError(
                "student_model",
                (
                    f"Schema 3.0 event failed status={parsed.status.model_dump()} "
                    f"body={response}"
                ),
            )
        return parsed

    def _local_response(self, context: AdapterContext) -> StudentModelResult:
        """Return the stable in-process learner-state snapshot."""

        return StudentModelResult(
            mastery_status="DEVELOPING",
            continuity_status="on_track",
            recommended_entry_phase=None,
            hint_dependency_score=0.0,
            intervention_required=False,
            intervention_reason=None,
        )


class MockStudentModelAdapter(StudentModelServiceAdapter):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(
            Settings(
                student_model_url="",
                student_model_topic_ids={},
                use_mock_student_model=True,
            )
        )
