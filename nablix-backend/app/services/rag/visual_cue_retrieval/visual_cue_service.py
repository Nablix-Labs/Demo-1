"""
Visual cue retrieval service for AD-401.

Core logic for POST /visual-cue/retrieve: queries Qdrant, filters by
concept_id/error_type/difficulty, excludes already-shown cues,
returns the most relevant visual cue with its relevance score.
"""

import logging

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("visual_cue_service")


def get_visual_cue(
    concept_id: str,
    error_type: str,
    difficulty: str,
    exclude_content_ids: list[str],
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
) -> dict | None:
    """
    Find the most relevant visual cue for a given error type and concept.

    How it works:
    1. Build a Qdrant filter for concept_id + error_type + difficulty
       + approval_status=APPROVED
    2. Generate a query embedding from those parameters
    3. Run vector similarity search
    4. Skip any cue whose content_id is in exclude_content_ids
    5. Return the best match with its relevance score, or None

    The relevance_score comes from Qdrant's cosine similarity.
    Higher score = better match.
    """

    # 1. Build filter conditions
    must_conditions = [
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="error_type", match=MatchValue(value=error_type)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
        FieldCondition(key="approval_status", match=MatchValue(value="APPROVED")),
    ]
    query_filter = Filter(must=must_conditions)

    # 2. Build query text for embedding
    # We describe what we're looking for so the embedding captures the intent
    query_text = (
        f"visual cue for {error_type} error "
        f"in {concept_id} at {difficulty} difficulty"
    )

    query_embedding = openai_client.embeddings.create(
        input=query_text,
        model=config.EMBEDDING_MODEL,
    ).data[0].embedding

    # 3. Search Qdrant
    search_limit = len(exclude_content_ids) + 5

    search_response = qdrant_client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_embedding,
        using="text",
        query_filter=query_filter,
        limit=search_limit,
        with_payload=True,
    )

    # 4. Find the best unseen cue
    for hit in search_response.points:
        payload = hit.payload
        content_id = payload.get("content_id", "")

        if content_id in exclude_content_ids:
            continue

        # Qdrant returns a score -- for cosine similarity, higher is better
        relevance_score = hit.score if hit.score is not None else 0.0

        # 5. Return the visual cue
        result = {
            "content_id": content_id,
            "concept_id": payload.get("concept_id", ""),
            "visual_cue_type": payload.get("visual_cue_type", ""),
            "text": payload.get("text", ""),
            "voice_text": payload.get("voice_text"),
            "error_type": payload.get("error_type", ""),
            "difficulty": payload.get("difficulty", ""),
            "topic": payload.get("topic", ""),
            "subtopic": payload.get("subtopic", ""),
            "relevance_score": round(relevance_score, 4),
            "approval_status": payload.get("approval_status", ""),
        }

        logger.info(
            f"VISUAL_CUE_SERVED: content_id={content_id}, "
            f"concept={concept_id}, error_type={error_type}, "
            f"difficulty={difficulty}, score={relevance_score:.4f}"
        )
        return result

    # No matching visual cue found
    logger.info(
        f"NO_VISUAL_CUE: concept={concept_id}, error_type={error_type}, "
        f"difficulty={difficulty}"
    )
    return None


def count_available_cues(
    concept_id: str,
    error_type: str,
    difficulty: str,
    qdrant_client: QdrantClient,
) -> int:
    """Count how many visual cues exist for a given concept/error_type/difficulty."""
    query_filter = Filter(must=[
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="error_type", match=MatchValue(value=error_type)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
        FieldCondition(key="approval_status", match=MatchValue(value="APPROVED")),
    ])

    result = qdrant_client.count(
        collection_name=config.QDRANT_COLLECTION,
        count_filter=query_filter,
        exact=True,
    )
    return result.count
