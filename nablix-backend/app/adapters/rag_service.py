import asyncio
import time

from pydantic import ValidationError

from app.adapters.http_utils import JsonObject
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, RAGResult, RetrievedDocument
from app.models.rag import RAGRetrieveRequest, RAGRetrieveResponse
from app.services.rag_retrieval import retrieve_content


def _resolved_hint_level(context: AdapterContext, hint_level: int | None) -> int:
    if hint_level in (1, 2, 3):
        return hint_level
    if context.current_hint_level is not None:
        return min(context.current_hint_level + 1, 3)
    return min(max(context.attempt_count or 1, 1), 3)


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
        payload: JsonObject = self._build_retrieve_payload(
            request, error_type, hint_level
        )
        try:
            retrieve_request = RAGRetrieveRequest.model_validate(payload)
        except ValidationError as error:
            raise AdapterError(
                "rag_service",
                f"invalid internal retrieve request payload={payload}: {error}",
            ) from error
        response: RAGRetrieveResponse = await asyncio.to_thread(
            retrieve_content, retrieve_request, self._settings
        )
        return self.parse_response(response.model_dump())

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
            "hint_level": _resolved_hint_level(context, hint_level),
            "error_type": error_type,
            "difficulty": "FOUNDATION",
            "input_source": context.input_source or "TEXT",
            "max_results": 3,
            "exclude_content_ids": [],
        }

    def parse_response(self, response: dict[str, object]) -> RAGResult:
        try:
            parsed = RAGRetrieveResponse.model_validate(response)
            documents: list[RetrievedDocument] = [
                RetrievedDocument(
                    title=result.content_id,
                    content=result.text,
                    source=result.concept_id,
                )
                for result in parsed.results
            ]
            best_score: float = max(
                (result.relevance_score for result in parsed.results), default=0.0
            )

            return RAGResult(
                documents=documents,
                retrieval_confidence=best_score,
            )
        except ValidationError as error:
            raise AdapterError(
                "rag_service",
                f"invalid response body={response}: {error}",
            ) from error

    def _local_response(self, request: AdapterContext) -> RAGResult:
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
        super().__init__(Settings())

    async def call(
        self,
        request: AdapterContext,
        *,
        error_type: str | None,
        hint_level: int | None,
    ) -> RAGResult:
        del error_type, hint_level
        return self._local_response(request)
