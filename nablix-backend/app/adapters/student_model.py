"""Student Model adapter backed by Saravanan's HTTP contract."""

import json
from datetime import datetime, timedelta, timezone

import jwt
from pydantic import ValidationError

from app.adapters.http_utils import get_bytes, post_json
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
from app.models.topic_event_history import TopicEventHistoryResponse
from app.models.work_artifact import (
    Phase4ReviewPersistRequest,
    WorkArtifactPersistRequest,
    WorkArtifactPersistResponse,
)
from app.services.student_model_debug import record_request, record_response

# Minted per call rather than cached: HMAC signing is microseconds, and a short
# life means a leaked token is worth almost nothing.
_SERVICE_TOKEN_TTL_SECONDS = 300
# Identifies the caller in Student Model's logs. Not a user id and not looked
# up anywhere -- internal_service never resolves a student row.
_SERVICE_TOKEN_SUBJECT = "nablix-backend"


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
        """Serialize one Schema 3.0 event, persist it, and validate its full state."""

        url = self._require_student_model_url("Schema 3.0 session events")
        request_body = event.model_dump(mode="json", exclude_none=True)
        record_request(request_body)
        try:
            response = await post_json(
                "student_model",
                f"{url}/session/event",
                request_body,
                {"Authorization": f"Bearer {access_token}"},
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
        except AdapterRequestRejected as error:
            record_response(
                {
                    "status_code": error.status_code,
                    "response_body": error.response_body,
                }
            )
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
        except AdapterError as error:
            record_response({"error": str(error)})
            raise
        record_response(response)
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

    async def persist_work_artifact(
        self,
        request: WorkArtifactPersistRequest,
        access_token: str,
    ) -> WorkArtifactPersistResponse:
        """Store one attempt's canvas work and return its storage references."""

        url = self._require_student_model_url("work artifacts")
        response = await post_json(
            "student_model",
            f"{url}/work-artifacts",
            request.model_dump(mode="json"),
            {"Authorization": f"Bearer {access_token}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )
        try:
            return WorkArtifactPersistResponse.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid work artifact response body={response}: {error}",
            ) from error

    async def persist_phase4_review(
        self,
        request: Phase4ReviewPersistRequest,
    ) -> None:
        """Store the finished review on the topic learning summary.

        Takes no caller token on purpose: this WRITES the student's topic
        learning summary, which is orchestration, not something a student's own
        credential should be able to do.
        """

        url = self._require_student_model_url("Phase 4 review persistence")
        await post_json(
            "student_model",
            f"{url}/phase4-review",
            request.model_dump(mode="json"),
            {"Authorization": f"Bearer {self._service_token()}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )

    async def fetch_work_artifact_pdf(
        self,
        artifact_id: str,
        access_token: str,
    ) -> tuple[bytes, str]:
        """Fetch one stored work artifact's PDF bytes, forwarding the caller's
        own token -- never a service token, since Student Model enforces
        per-student ownership on this read."""

        url = self._require_student_model_url("work artifact PDF")
        return await get_bytes(
            "student_model",
            f"{url}/work-artifacts/{artifact_id}/pdf",
            {"Authorization": f"Bearer {access_token}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )

    async def fetch_topic_event_history(
        self,
        student_id: str,
        topic_id: str,
    ) -> TopicEventHistoryResponse:
        """Read the student's whole journey through one topic, for Phase 4.

        Service-authenticated, not caller-authenticated: this reads across the
        student's entire topic journey rather than one owned record, and
        Student Model gates it on internal_service accordingly.
        """

        url = self._require_student_model_url("topic event history")
        response = await post_json(
            "student_model",
            f"{url}/topic/event-history",
            {"student_id": student_id, "topic_id": topic_id},
            {"Authorization": f"Bearer {self._service_token()}"},
            self._settings.adapter_request_timeout_seconds,
            self._settings.adapter_request_retry_count,
        )
        try:
            return TopicEventHistoryResponse.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "student_model",
                f"invalid topic event history body={response}: {error}",
            ) from error

    def _service_token(self) -> str:
        """Mint an internal_service bearer for Student Model's Phase 4 endpoints.

        `/topic/event-history` and `/phase4-review` are
        `require_role("internal_service")` with no student branch
        (mathtutor-student app/api/routers/phase4.py), so forwarding the
        student's own token -- which is all this service had until now -- was a
        guaranteed 403, swallowed into "no review generated". The claims mirror
        mathtutor-student's own `create_access_token`: `sub`, `role`, `tier`,
        `iat`, `exp`, HS256 over the shared secret.
        """

        secret = self._settings.student_model_jwt_secret
        if secret == "":
            raise AdapterError(
                "student_model",
                "NABLIX_STUDENT_MODEL_JWT_SECRET is required for Phase 4 review calls",
            )
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": _SERVICE_TOKEN_SUBJECT,
                "role": "internal_service",
                # Not checked for this role, but CurrentUser reads the claim
                # unconditionally and would KeyError without it.
                "tier": "basic",
                "iat": now,
                "exp": now + timedelta(seconds=_SERVICE_TOKEN_TTL_SECONDS),
            },
            secret,
            algorithm=self._settings.student_model_jwt_algorithm,
        )

    def _require_student_model_url(self, purpose: str) -> str:
        if self._settings.use_mock_student_model:
            raise AdapterError(
                "student_model",
                f"{purpose} require NABLIX_USE_MOCK_STUDENT_MODEL=false",
            )
        if self._settings.student_model_url == "":
            raise AdapterError(
                "student_model",
                f"NABLIX_STUDENT_MODEL_URL is required for {purpose}",
            )
        return self._settings.student_model_url.rstrip("/")

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
