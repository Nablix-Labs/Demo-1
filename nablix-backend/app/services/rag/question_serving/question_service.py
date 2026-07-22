"""
Question retrieval service for AD-300.

Core logic for POST /question/next: queries Qdrant, filters by
phase/difficulty/concept, excludes previously seen questions,
returns the next question.
"""

import logging

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, HasIdCondition

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("question_service")


def get_next_question(
    concept_id: str,
    phase: str,
    difficulty: str,
    previously_seen_ids: list[str],
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
) -> dict | None:
    """
    Find the next unseen question matching concept/phase/difficulty.

    How it works:
    1. Build a Qdrant filter for concept_id + phase + difficulty
    2. Generate a query embedding from those parameters
    3. Run vector similarity search
    4. Skip any question whose question_id is in previously_seen_ids
    5. Return the first match, or None if all questions have been seen

    Returns a dict with question_id, question_text, correct_answer, etc.
    Returns None if no unseen questions match the filters.
    """

    # 1. Build filter conditions
    must_conditions = [
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="phase", match=MatchValue(value=phase)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
    ]
    query_filter = Filter(must=must_conditions)

    # 2. Build query text for embedding
    query_text = f"concept: {concept_id} | phase: {phase} | difficulty: {difficulty}"

    query_embedding = openai_client.embeddings.create(
        input=query_text,
        model=config.EMBEDDING_MODEL,
    ).data[0].embedding

    # 3. Search Qdrant
    # Request extra results to account for filtering out previously seen
    search_limit = len(previously_seen_ids) + 5

    search_response = qdrant_client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_embedding,
        using="text",
        query_filter=query_filter,
        limit=search_limit,
    )

    # 4. Find the first unseen question
    for hit in search_response.points:
        payload = hit.payload
        question_id = payload.get("question_id", "")

        if question_id in previously_seen_ids:
            continue

        # 5. Return the question
        result = {
            "question_id": question_id,
            "question_text": payload.get("question_text", ""),
            "correct_answer": payload.get("correct_answer", ""),
            "difficulty": payload.get("difficulty", ""),
            "phase": payload.get("phase", ""),
            "concept_id": payload.get("concept_id", ""),
            "topic": payload.get("topic", ""),
            "subtopic": payload.get("subtopic", ""),
            "voice_text": payload.get("voice_text"),
        }

        logger.info(
            f"QUESTION_SERVED: question_id={question_id}, "
            f"concept={concept_id}, phase={phase}, difficulty={difficulty}, "
            f"seen_count={len(previously_seen_ids)}"
        )
        return result

    # No unseen questions found
    logger.info(
        f"NO_QUESTIONS: concept={concept_id}, phase={phase}, "
        f"difficulty={difficulty}, seen_count={len(previously_seen_ids)}"
    )
    return None


def get_diagnostic_question(
    concept_id: str,
    difficulty: str,
    previously_seen_ids: list[str],
    qdrant_client: QdrantClient,
    openai_client: OpenAI,
) -> dict | None:
    """
    Find the next unseen DIAGNOSTIC question for a concept/difficulty.

    Same logic as get_next_question() but:
    - Phase is always DIAGNOSTIC (hardcoded, not a parameter)
    - Returns extra fields: diagnostic_purpose, expected_method

    These extra fields tell the AI engine why we're asking this question
    and what method the student should use. This helps the engine
    interpret the student's response and decide what to do next.
    """

    # 1. Build filter -- phase is always DIAGNOSTIC
    must_conditions = [
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="phase", match=MatchValue(value="DIAGNOSTIC")),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
    ]
    query_filter = Filter(must=must_conditions)

    # 2. Build query text for embedding
    query_text = f"concept: {concept_id} | phase: DIAGNOSTIC | difficulty: {difficulty}"

    query_embedding = openai_client.embeddings.create(
        input=query_text,
        model=config.EMBEDDING_MODEL,
    ).data[0].embedding

    # 3. Search Qdrant
    search_limit = len(previously_seen_ids) + 5

    search_response = qdrant_client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_embedding,
        using="text",
        query_filter=query_filter,
        limit=search_limit,
    )

    # 4. Find the first unseen question
    for hit in search_response.points:
        payload = hit.payload
        question_id = payload.get("question_id", "")

        if question_id in previously_seen_ids:
            continue

        # 5. Return question with diagnostic-specific fields
        result = {
            "question_id": question_id,
            "question_text": payload.get("question_text", ""),
            "correct_answer": payload.get("correct_answer", ""),
            "difficulty": payload.get("difficulty", ""),
            "phase": payload.get("phase", ""),
            "concept_id": payload.get("concept_id", ""),
            "topic": payload.get("topic", ""),
            "subtopic": payload.get("subtopic", ""),
            "voice_text": payload.get("voice_text"),
            "diagnostic_purpose": payload.get("diagnostic_purpose"),
            "expected_method": payload.get("expected_method"),
        }

        logger.info(
            f"DIAGNOSTIC_SERVED: question_id={question_id}, "
            f"concept={concept_id}, difficulty={difficulty}, "
            f"seen_count={len(previously_seen_ids)}"
        )
        return result

    # No unseen diagnostic questions found
    logger.info(
        f"NO_DIAGNOSTIC: concept={concept_id}, difficulty={difficulty}, "
        f"seen_count={len(previously_seen_ids)}"
    )
    return None


def count_available_questions(
    concept_id: str,
    phase: str,
    difficulty: str,
    qdrant_client: QdrantClient,
) -> int:
    """Count how many questions exist for a given concept/phase/difficulty."""
    query_filter = Filter(must=[
        FieldCondition(key="concept_id", match=MatchValue(value=concept_id)),
        FieldCondition(key="phase", match=MatchValue(value=phase)),
        FieldCondition(key="difficulty", match=MatchValue(value=difficulty)),
    ])

    result = qdrant_client.count(
        collection_name=config.QDRANT_COLLECTION,
        count_filter=query_filter,
        exact=True,
    )
    return result.count
