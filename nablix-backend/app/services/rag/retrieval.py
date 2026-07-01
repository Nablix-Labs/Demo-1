import time
import logging
from dataclasses import dataclass, field

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Condition

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("retrieval")

@dataclass
class RetrievalRequest:
    query_id: str
    concept_id: str
    content_type: str
    hint_level: int | None = None
    error_type: str | None = None
    difficulty: str = "FOUNDATION"
    input_source: str = "TEXT"
    max_results: int = 3
    exclude_content_ids: list[str] = field(default_factory=list)

@dataclass
class RetrievalResultItem:
    content_id: str
    content_type: str
    hint_level: int | None
    text: str
    voice_text: str | None
    relevance_score: float
    concept_id: str
    error_type: str | None
    difficulty: str
    version: str
    approval_status: str

@dataclass
class RetrievalResponse:
    query_id: str
    results: list[RetrievalResultItem]
    result_count: int
    fallback_used: bool
    query_metadata: dict

def build_filters(request: RetrievalRequest) -> Filter:
    must_conditions: list[Condition] = [
        FieldCondition(key="approval_status", match=MatchValue(value="APPROVED")),
        FieldCondition(key="concept_id", match=MatchValue(value=request.concept_id)),
        FieldCondition(key="content_type", match=MatchValue(value=request.content_type)),
    ]

    if request.error_type:
        must_conditions.append(
            FieldCondition(key="error_type", match=MatchValue(value=request.error_type))
        )

    if request.difficulty:
        must_conditions.append(
            FieldCondition(key="difficulty", match=MatchValue(value=request.difficulty))
        )

    if request.hint_level is not None:
        must_conditions.append(
            FieldCondition(key="hint_level", match=MatchValue(value=request.hint_level))
        )

    return Filter(must=must_conditions)

def build_query_text(request: RetrievalRequest) -> str:
    parts = [
        f"concept: {request.concept_id}",
        f"type: {request.content_type}",
        f"difficulty: {request.difficulty}",
    ]
    if request.error_type:
        parts.append(f"error: {request.error_type}")
    if request.hint_level is not None:
        parts.append(f"hint level: {request.hint_level}")

    return " | ".join(parts)

def retrieve(
    request: RetrievalRequest,
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
) -> RetrievalResponse:
    start_time = time.time()

    query_filter = build_filters(request)
    filters_applied = ["concept_id", "content_type", "approval_status"]
    if request.error_type:
        filters_applied.append("error_type")
    if request.difficulty:
        filters_applied.append("difficulty")
    if request.hint_level is not None:
        filters_applied.append("hint_level")

    query_text = build_query_text(request)

    vector_name = "voice_text" if request.input_source == "VOICE" else "text"

    query_embedding = openai_client.embeddings.create(
        input=query_text,
        model=config.EMBEDDING_MODEL,
    ).data[0].embedding

    search_limit = request.max_results + len(request.exclude_content_ids)

    search_response = qdrant_client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_embedding,
        using=vector_name,
        query_filter=query_filter,
        limit=search_limit,
    )

    results = []
    for hit in search_response.points:
        payload = hit.payload
        if payload is None:  # skip hits with no payload — nothing to return
            continue
        content_id = payload.get("content_id", "")

        if content_id in request.exclude_content_ids:
            continue

        if len(results) >= request.max_results:
            break

        display_text = payload.get("text", "")
        voice_text = payload.get("voice_text")

        result_item = RetrievalResultItem(
            content_id=content_id,
            content_type=payload.get("content_type", ""),
            hint_level=payload.get("hint_level"),
            text=display_text,
            voice_text=voice_text,
            relevance_score=round(hit.score, 4),
            concept_id=payload.get("concept_id", ""),
            error_type=payload.get("error_type"),
            difficulty=payload.get("difficulty", ""),
            version=payload.get("version", ""),
            approval_status=payload.get("approval_status", ""),
        )
        results.append(result_item)

    elapsed_ms = round((time.time() - start_time) * 1000)
    fallback_used = len(results) == 0

    response = RetrievalResponse(
        query_id=request.query_id,
        results=results,
        result_count=len(results),
        fallback_used=fallback_used,
        query_metadata={
            "retrieval_time_ms": elapsed_ms,
            "filters_applied": filters_applied,
        },
    )

    logger.info(
        f"RETRIEVAL: query_id={request.query_id}, "
        f"concept={request.concept_id}, type={request.content_type}, "
        f"results={len(results)}, fallback={fallback_used}, "
        f"time_ms={elapsed_ms}"
    )

    return response

def response_to_dict(response: RetrievalResponse) -> dict:
    return {
        "query_id": response.query_id,
        "results": [
            {
                "content_id": r.content_id,
                "content_type": r.content_type,
                "hint_level": r.hint_level,
                "text": r.text,
                "voice_text": r.voice_text,
                "relevance_score": r.relevance_score,
                "concept_id": r.concept_id,
                "error_type": r.error_type,
                "difficulty": r.difficulty,
                "version": r.version,
                "approval_status": r.approval_status,
            }
            for r in response.results
        ],
        "result_count": response.result_count,
        "fallback_used": response.fallback_used,
        "query_metadata": response.query_metadata,
    }
