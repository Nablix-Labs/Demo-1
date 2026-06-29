"""RAG service adapter.

The application asks for retrieved learning context with `retrieve`. The
adapter then either returns deterministic curriculum snippets for development
or POSTs the shared `AdapterContext` to the configured RAG service.
"""

from typing import NoReturn

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, RAGResult, RetrievedDocument


class RAGServiceAdapterClient:
    """Retrieves curriculum documents from mock data or the RAG service URL."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def retrieve(self, context: AdapterContext) -> RAGResult:
        """Service-facing method used by the tutor pipeline."""

        return await self.call(context)

    async def call(self, request: AdapterContext) -> RAGResult:
        """Return mock context or call the live RAG service based on settings."""

        if self._settings.use_mock_rag:
            return self._mock_response(request)

        payload: JsonObject = request.model_dump(mode="json")
        try:
            response = await post_json(
                "rag_service",
                self._settings.rag_service_url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def parse_response(self, response: dict[str, object]) -> RAGResult:
        try:
            return RAGResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "rag_service",
                f"invalid response body={response}: {error}",
            ) from error

    def handle_error(self, error: AdapterError) -> NoReturn:
        raise error

    def _mock_response(self, request: AdapterContext) -> RAGResult:
        """Return stable curriculum context shaped like the real service result."""

        return RAGResult(
            documents=[
                RetrievedDocument(
                    title="Arithmetic review",
                    content="Addition and subtraction errors often come from skipping place value checks.",
                    source="mock_curriculum",
                )
            ],
            retrieval_confidence=0.91,
        )


class MockRAGServiceAdapter(RAGServiceAdapterClient):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(Settings(use_mock_rag=True))
