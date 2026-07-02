import os
import time
import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI
from qdrant_client import QdrantClient

import config
from retrieval import (
    RetrievalRequest,
    retrieve,
    response_to_dict,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("server")

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

if config.QDRANT_URL and config.QDRANT_API_KEY:
    logger.info(f"Connecting to Qdrant Cloud at: {config.QDRANT_URL}")
    qdrant_client = QdrantClient(
        url=config.QDRANT_URL,
        api_key=config.QDRANT_API_KEY,
    )
else:
    qdrant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
    logger.info(f"Using local Qdrant at: {qdrant_path}")
    qdrant_client = QdrantClient(path=qdrant_path)

class RetrievalRequestBody(BaseModel):
    query_id: str
    concept_id: str
    content_type: str
    hint_level: int | None = None
    error_type: str | None = None
    difficulty: str = "FOUNDATION"
    input_source: str = "TEXT"
    max_results: int = 3
    exclude_content_ids: list[str] = Field(default_factory=list)

app = FastAPI(
    title="Nablix Math Tutor - Knowledge Base API",
    description="Retrieval endpoint for the AI Math Tutor knowledge base",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def warm_rag_cache():
    """Pre-warm the cache for common demo concepts at startup.

    The first RAG call for a concept takes ~2-4 seconds (embedding +
    Qdrant).  By pre-querying the demo concept on startup, the first
    student interaction is just as fast as subsequent ones.
    """
    demo_concepts = [
        ("ALG_LINEAR_ONE_STEP_ADDITION", "EXPLANATION", None),
        ("ALG_LINEAR_ONE_STEP_ADDITION", "HINT", 1),
        ("ALG_LINEAR_ONE_STEP_ADDITION", "HINT", 2),
        ("ALG_LINEAR_ONE_STEP_ADDITION", "HINT", 3),
    ]
    for concept_id, content_type, hint_level in demo_concepts:
        try:
            body = RetrievalRequestBody(
                query_id="warmup",
                concept_id=concept_id,
                content_type=content_type,
                hint_level=hint_level,
            )
            retrieve_endpoint(body)
            logger.info(f"Cache warmed: {concept_id}/{content_type}/hint={hint_level}")
        except Exception as e:
            logger.warning(f"Cache warm failed for {concept_id}/{content_type}: {e}")


@app.get("/health")
def health_check():
    return {"status": "ok", "qdrant_cloud": bool(config.QDRANT_URL)}

# ---- Retrieval cache ----
# The same (concept_id, content_type, hint_level, difficulty, error_type,
# input_source) always produces the same embedding and Qdrant results.
# Caching avoids repeated OpenAI embedding calls (~500ms) and Qdrant
# queries (~500-1000ms) for the same concept during a tutoring session.
# Cache holds up to 64 entries; entries are evicted LRU-style.
_retrieval_cache: dict[str, tuple[float, dict]] = {}
_CACHE_MAX_SIZE = 64
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_key(body: RetrievalRequestBody) -> str:
    return f"{body.concept_id}|{body.content_type}|{body.hint_level}|{body.difficulty}|{body.error_type}|{body.input_source}"


def _get_cached(key: str) -> dict | None:
    entry = _retrieval_cache.get(key)
    if entry is None:
        return None
    cached_at, result = entry
    if time.time() - cached_at > _CACHE_TTL_SECONDS:
        del _retrieval_cache[key]
        return None
    return result


def _put_cache(key: str, result: dict) -> None:
    if len(_retrieval_cache) >= _CACHE_MAX_SIZE:
        oldest_key = min(_retrieval_cache, key=lambda k: _retrieval_cache[k][0])
        del _retrieval_cache[oldest_key]
    _retrieval_cache[key] = (time.time(), result)


@app.post("/retrieve")
def retrieve_endpoint(body: RetrievalRequestBody):
    try:
        # Check cache first — same concept + content type = same results
        cache_key = _cache_key(body)
        cached = _get_cached(cache_key)
        if cached is not None:
            logger.info(f"CACHE HIT: {cache_key} (skipping embedding + Qdrant)")
            # Return cached result with the current query_id
            cached["query_id"] = body.query_id
            return cached

        request = RetrievalRequest(
            query_id=body.query_id,
            concept_id=body.concept_id,
            content_type=body.content_type,
            hint_level=body.hint_level,
            error_type=body.error_type,
            difficulty=body.difficulty,
            input_source=body.input_source,
            max_results=body.max_results,
            exclude_content_ids=body.exclude_content_ids,
        )

        response = retrieve(request, qdrant_client, openai_client)
        result = response_to_dict(response)

        # Cache the result (only if we got results)
        if not body.exclude_content_ids:
            _put_cache(cache_key, result)

        return result

    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
