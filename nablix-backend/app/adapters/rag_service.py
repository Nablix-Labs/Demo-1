import time
from typing import NoReturn

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, RAGResult, RetrievedDocument


class RAGServiceAdapterClient:

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def retrieve(
        self,
        context: AdapterContext,
        *,
        error_type: str | None,
        hint_level: int | None,
    ) -> RAGResult:
        return await self.call(context, error_type=error_type, hint_level=hint_level)

    async def call(
        self,
        request: AdapterContext,
        *,
        error_type: str | None,
        hint_level: int | None,
    ) -> RAGResult:
        if self._settings.use_mock_rag:
            return self._mock_response(request)

        payload: JsonObject = self._build_retrieve_payload(request, error_type, hint_level)
        url = self._settings.rag_service_url.rstrip("/") + "/retrieve"

        try:
            response = await post_json(
                "rag_service",
                url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def _build_retrieve_payload(
        self,
        context: AdapterContext,
        error_type: str | None,
        hint_level: int | None,
    ) -> JsonObject:
        # Only reached for GUIDED_HINT (gated in run_tutor_pipeline), so the target
        # content is always a hint at the classifier's chosen level.
        return {
            "query_id": f"{context.session_id}-{int(time.time())}",
            "concept_id": context.concept_id or "ALG_LINEAR_ONE_STEP_ADDITION",
            "content_type": "HINT",
            "hint_level": hint_level,
            "error_type": error_type,
            "difficulty": "FOUNDATION",
            "input_source": context.input_source or "TEXT",
            "max_results": 3,
            "exclude_content_ids": [],
        }

    def parse_response(self, response: dict[str, object]) -> RAGResult:
        try:
            results = response.get("results", [])

            documents = []
            best_score = 0.0
            for r in results:
                documents.append(RetrievedDocument(
                    title=r.get("content_id", ""),
                    content=r.get("text", ""),
                    source=r.get("concept_id", ""),
                ))
                score = r.get("relevance_score", 0.0)
                if score > best_score:
                    best_score = score

            return RAGResult(
                documents=documents,
                retrieval_confidence=best_score if documents else 0.0,
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise AdapterError(
                "rag_service",
                f"invalid response body={response}: {error}",
            ) from error

    def handle_error(self, error: AdapterError) -> NoReturn:
        raise error

    def _mock_response(self, request: AdapterContext) -> RAGResult:
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

    def __init__(self) -> None:
        super().__init__(Settings(use_mock_rag=True))
