"""Student Model adapter backed by Saravanan's HTTP contract."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, StudentModelEvent, StudentModelResult
from app.models.student_model import StudentModelSessionEvent, StudentModelSessionResponse


_CONFIG_PATH: Path = (
    Path(__file__).resolve().parents[2] / "configs" / "student_model_integration.yaml"
)


class StudentModelIntegrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint_path: str
    schema_version: str


@lru_cache(maxsize=1)
def load_student_model_integration_config() -> StudentModelIntegrationConfig:
    raw_config: object = yaml.safe_load(_CONFIG_PATH.read_text())
    return StudentModelIntegrationConfig.model_validate(raw_config)


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
        # phase; gating it to Independent Practice starves Saravanan's guided
        # advancement rule.
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

    async def send_session_event(
        self,
        event: StudentModelSessionEvent,
    ) -> StudentModelSessionResponse:
        """Forward one schema-3 journey event without changing its event fields."""

        if self._settings.student_model_base_url == "":
            raise AdapterError(
                "student_model",
                "NABLIX_STUDENT_MODEL_BASE_URL is required for Demo 3 learning events",
            )
        if self._settings.student_model_token == "":
            raise AdapterError(
                "student_model",
                "NABLIX_STUDENT_MODEL_TOKEN is required for Demo 3 learning events",
            )

        integration_config = load_student_model_integration_config()
        payload: JsonObject = event.model_dump(exclude_none=True)
        response = await post_json(
            "student_model",
            (
                f"{self._settings.student_model_base_url.rstrip('/')}"
                f"{integration_config.endpoint_path}"
            ),
            payload,
            {"Authorization": f"Bearer {self._settings.student_model_token}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )
        try:
            parsed = StudentModelSessionResponse.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid schema-3 response body={response}: {error}",
            ) from error
        if parsed.schema_version != integration_config.schema_version:
            raise AdapterError(
                "student_model",
                (
                    f"unsupported schema_version={parsed.schema_version} "
                    f"expected={integration_config.schema_version} body={response}"
                ),
            )
        if parsed.request_id != event.request_id:
            raise AdapterError(
                "student_model",
                (
                    f"response request_id={parsed.request_id} does not match "
                    f"request_id={event.request_id} body={response}"
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
