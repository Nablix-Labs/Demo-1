"""Student Model adapter backed by Saravanan's HTTP contract."""

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, StudentModelEvent, StudentModelResult


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
        topic_id = self._settings.student_model_topic_ids.get(concept_id)
        if topic_id is None:
            raise AdapterError(
                "student_model",
                f"no topic_id mapping configured for concept_id={concept_id}",
            )

        # independent_success is Sanya's "correct without help" flag in ANY
        # phase — verified live: Saravanan promotes GUIDED -> INDEPENDENT after
        # three of these, so gating it to Independent Practice starves his gate.
        payload: JsonObject = {
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
