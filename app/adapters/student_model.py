"""Student Model adapter backed by Saravanan's HTTP contract."""

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, StudentModelEvent, StudentModelResult
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

    async def update_from_event(
        self,
        event: StudentModelEvent,
        context: AdapterContext,
        access_token: str,
    ) -> StudentModelResult:
        """Persist one evaluated event and return the authoritative learner state."""

        if self._settings.use_mock_student_model:
            return self._local_response(context)
        if self._settings.student_model_url == "":
            raise AdapterError(
                "student_model",
                "NABLIX_STUDENT_MODEL_URL is required when NABLIX_USE_MOCK_STUDENT_MODEL=false",
            )

        concept_id = context.concept_id
        if concept_id is None:
            raise AdapterError(
                "student_model",
                "concept_id is required for Student Model updates",
            )
        source_turn_id: str | None = context.source_turn_id
        if source_turn_id is None:
            raise AdapterError(
                "student_model",
                "source_turn_id is required for Student Model updates",
            )
        topic_id = self._settings.student_model_topic_ids.get(concept_id)
        if topic_id is None:
            raise AdapterError(
                "student_model",
                f"no topic_id mapping configured for concept_id={concept_id}",
            )

        # independent_success is Sanya's "correct without help" flag in ANY
        # phase; gating it to Independent Practice starves Saravanan's guided
        # advancement rule.
        payload: JsonObject = {
            "event_id": f"{context.session_id}:{source_turn_id}:{event.event_type}",
            "source_turn_id": source_turn_id,
            "topic_id": topic_id,
            "event_type": event.event_type,
            "evaluation": event.evaluation,
            "error_type": event.error_type,
            "hint_level_used": event.hint_level_used,
            "independent_success": event.independent_success,
            "current_phase": context.current_phase,
            "independent_correct_in_session": (
                context.independent_correct_in_session + int(event.independent_success)
            ),
        }
        response = await post_json(
            "student_model",
            f"{self._settings.student_model_url.rstrip('/')}/interaction",
            payload,
            {"Authorization": f"Bearer {access_token}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )
        return self.parse_response(response)

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
        response = await post_json(
            "student_model",
            f"{self._settings.student_model_url.rstrip('/')}/session/event",
            event.model_dump(exclude_none=True),
            {"Authorization": f"Bearer {access_token}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )
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
