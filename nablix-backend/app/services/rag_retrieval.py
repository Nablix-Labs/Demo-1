import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from openai import APIError, OpenAI
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.rag import (
    RAGQueryMetadata,
    RAGRetrieveRequest,
    RAGRetrieveResponse,
    RAGRetrievedContent,
)


_Result = TypeVar("_Result")
_RETRIABLE_QDRANT_ERRORS = (
    ResponseHandlingException,
    UnexpectedResponse,
    httpx.HTTPError,
)
# Cached per process; serverless workers reuse them across warm invocations.
_clients: tuple[OpenAI, QdrantClient] | None = None


def _get_clients(settings: Settings) -> tuple[OpenAI, QdrantClient]:
    global _clients
    if _clients is None:
        _clients = (
            OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_request_timeout_seconds,
                # The SDK retries natively; no hand-rolled loop needed here.
                max_retries=settings.adapter_request_retry_count,
            ),
            QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                timeout=settings.adapter_request_timeout_seconds,
            ),
        )
    return _clients


def _require_settings(settings: Settings) -> None:
    missing: list[str] = []
    if settings.openai_api_key == "":
        missing.append("NABLIX_OPENAI_API_KEY")
    if settings.qdrant_url == "":
        missing.append("NABLIX_QDRANT_URL")
    if settings.qdrant_api_key == "":
        missing.append("NABLIX_QDRANT_API_KEY")
    if missing:
        raise AdapterError(
            "rag_service",
            f"missing required environment variables: {', '.join(missing)}",
        )


def _run_with_retries(
    operation: Callable[[], _Result],
    operation_name: str,
    attempts: int,
    retriable_errors: tuple[type[Exception], ...],
) -> _Result:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retriable_errors as error:
            last_error = error
            logger.warning(
                "rag_downstream_retry",
                extra={
                    "operation": operation_name,
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
    if last_error is None:
        raise RuntimeError(f"{operation_name} retry loop completed without a result")
    raise AdapterError(
        "rag_service",
        f"{operation_name} failed after {attempts} attempts: {last_error}",
    ) from last_error


def _embedding_query(request: RAGRetrieveRequest, concept_id: str) -> str:
    parts: list[str] = [
        f"concept: {concept_id}",
        f"content type: {request.content_type}",
        f"difficulty: {request.difficulty}",
    ]
    if request.error_type is not None:
        parts.append(f"error type: {request.error_type}")
    if request.hint_level is not None:
        parts.append(f"hint level: {request.hint_level}")
    return " | ".join(parts)


def _build_filter(
    request: RAGRetrieveRequest,
    concept_id: str,
) -> tuple[models.Filter, list[str]]:
    filter_values: list[tuple[str, str | int]] = [
        ("concept_id", concept_id),
        ("content_type", request.content_type),
        ("difficulty", request.difficulty),
        ("approval_status", "APPROVED"),
    ]
    if request.error_type is not None:
        filter_values.append(("error_type", request.error_type))
    if request.hint_level is not None:
        filter_values.append(("hint_level", request.hint_level))
    conditions: list[models.Condition] = [
        models.FieldCondition(
            key=field_name,
            match=models.MatchValue(value=value),
        )
        for field_name, value in filter_values
    ]
    return (
        models.Filter(must=conditions),
        [field_name for field_name, _value in filter_values],
    )


def _parse_result(payload: dict[str, object], score: float) -> RAGRetrievedContent:
    return RAGRetrievedContent.model_validate(
        {
            "content_id": payload.get("content_id"),
            "content_type": payload.get("content_type"),
            "hint_level": payload.get("hint_level"),
            "text": payload.get("text"),
            "voice_text": payload.get("voice_text"),
            "relevance_score": score,
            "concept_id": payload.get("concept_id"),
            "error_type": payload.get("error_type"),
            "difficulty": payload.get("difficulty"),
            "version": payload.get("version"),
            "approval_status": payload.get("approval_status"),
        }
    )


def retrieve_content(
    request: RAGRetrieveRequest,
    settings: Settings,
) -> RAGRetrieveResponse:
    started_at: float = time.monotonic()
    _require_settings(settings)
    concept_id: str = settings.qdrant_concept_id_map.get(
        request.concept_id, request.concept_id
    )
    attempts: int = settings.adapter_request_retry_count + 1
    openai_client, qdrant_client = _get_clients(settings)
    try:
        embedding_response = openai_client.embeddings.create(
            model=settings.embedding_model,
            input=_embedding_query(request, concept_id),
        )
    except APIError as error:
        raise AdapterError(
            "rag_service",
            f"OpenAI embedding request failed: {error}",
        ) from error
    embedding: list[float] = embedding_response.data[0].embedding
    query_filter, filters = _build_filter(request, concept_id)
    query_response = _run_with_retries(
        lambda: qdrant_client.query_points(
            collection_name=settings.qdrant_collection,
            query=embedding,
            using="voice_text" if request.input_source == "VOICE" else "text",
            query_filter=query_filter,
            limit=request.max_results + len(request.exclude_content_ids),
            with_payload=True,
        ),
        "Qdrant query",
        attempts,
        _RETRIABLE_QDRANT_ERRORS,
    )
    excluded: set[str] = set(request.exclude_content_ids)
    results: list[RAGRetrievedContent] = []
    for point in query_response.points:
        payload: dict[str, object] = point.payload or {}
        content_id: object = payload.get("content_id")
        if isinstance(content_id, str) and content_id in excluded:
            continue
        try:
            results.append(_parse_result(payload, point.score))
        except ValueError as error:
            raise AdapterError(
                "rag_service",
                f"invalid Qdrant payload point_id={point.id} payload={payload}: {error}",
            ) from error
        if len(results) == request.max_results:
            break
    elapsed_ms: int = round((time.monotonic() - started_at) * 1000)
    return RAGRetrieveResponse(
        query_id=request.query_id,
        results=results,
        result_count=len(results),
        fallback_used=len(results) == 0,
        query_metadata=RAGQueryMetadata(
            retrieval_time_ms=elapsed_ms,
            filters_applied=filters,
        ),
    )
