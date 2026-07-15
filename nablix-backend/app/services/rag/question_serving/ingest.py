"""
Ingestion script for AD-300 — Question Bank.

Reads question_bank.json, generates embeddings via OpenAI,
stores in a separate Qdrant collection (math_tutor_questions).

Usage:
    python ingest.py
    python ingest.py path/to/custom_questions.json
"""

import json
import os
import sys
import logging
import hashlib

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    PayloadSchemaType,
)

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_questions")


def get_embedding(client: OpenAI, text: str) -> list[float]:
    """Generate embedding for a text string using OpenAI."""
    response = client.embeddings.create(
        input=text,
        model=config.EMBEDDING_MODEL,
    )
    return response.data[0].embedding


def get_qdrant_client() -> QdrantClient:
    """Create Qdrant client -- cloud if credentials set, else local file storage."""
    if config.QDRANT_URL and config.QDRANT_API_KEY:
        logger.info(f"Connecting to Qdrant Cloud at: {config.QDRANT_URL}")
        return QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=60)

    qdrant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
    logger.info(f"Using local Qdrant at: {qdrant_path}")
    return QdrantClient(path=qdrant_path)


def setup_collection(client: QdrantClient):
    """Create the questions collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]

    if config.QDRANT_COLLECTION in collections:
        logger.info(f"Collection '{config.QDRANT_COLLECTION}' already exists, skipping creation.")
        _create_indexes(client)
        return

    client.create_collection(
        collection_name=config.QDRANT_COLLECTION,
        vectors_config={
            "text": VectorParams(
                size=config.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
            "voice_text": VectorParams(
                size=config.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        },
    )
    logger.info(f"Created collection '{config.QDRANT_COLLECTION}'")
    _create_indexes(client)


def _create_indexes(client: QdrantClient):
    """Create payload indexes for the fields we filter on during retrieval."""
    index_fields = {
        "concept_id": PayloadSchemaType.KEYWORD,
        "phase": PayloadSchemaType.KEYWORD,
        "difficulty": PayloadSchemaType.KEYWORD,
        "topic": PayloadSchemaType.KEYWORD,
        "subtopic": PayloadSchemaType.KEYWORD,
        "question_id": PayloadSchemaType.KEYWORD,
    }
    for field_name, field_type in index_fields.items():
        try:
            client.create_payload_index(
                collection_name=config.QDRANT_COLLECTION,
                field_name=field_name,
                field_schema=field_type,
            )
            logger.info(f"  Created index: {field_name}")
        except Exception as e:
            logger.info(f"  Index {field_name}: already exists or skipped ({e})")


def build_payload(question: dict) -> dict:
    """Convert a question dict to a Qdrant payload."""
    return {
        "question_id": question["question_id"],
        "concept_id": question["concept_id"],
        "topic": question["topic"],
        "subtopic": question["subtopic"],
        "phase": question["phase"],
        "difficulty": question["difficulty"],
        "question_text": question["question_text"],
        "correct_answer": question["correct_answer"],
        "voice_text": question.get("voice_text"),
        "age_band": question.get("age_band", "11-14"),
        "language": question.get("language", "en"),
    }


def ingest(input_path: str):
    """Main ingestion function. Read JSON, embed, store in Qdrant."""

    # 1. Read questions
    logger.info(f"Reading questions from: {input_path}")
    with open(input_path) as f:
        questions = json.load(f)
    logger.info(f"Loaded {len(questions)} questions")

    # 2. Validate required fields
    required_fields = ["question_id", "concept_id", "phase", "difficulty",
                       "question_text", "correct_answer", "topic", "subtopic"]
    valid_questions = []
    for i, q in enumerate(questions):
        missing = [f for f in required_fields if f not in q or not q[f]]
        if missing:
            logger.warning(f"Question {i} ({q.get('question_id', '?')}): missing fields {missing}, skipping")
        else:
            valid_questions.append(q)

    logger.info(f"{len(valid_questions)} questions passed validation")

    if not valid_questions:
        logger.error("No valid questions to ingest.")
        return

    # 3. Generate embeddings
    logger.info(f"Generating embeddings using model: {config.EMBEDDING_MODEL}")
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

    embedded = []
    for q in valid_questions:
        try:
            text_emb = get_embedding(openai_client, q["question_text"])
            voice_emb = None
            if q.get("voice_text"):
                voice_emb = get_embedding(openai_client, q["voice_text"])
            embedded.append((q, text_emb, voice_emb))
            logger.info(f"  Embedded: {q['question_id']}")
        except Exception as e:
            logger.error(f"  Failed to embed {q['question_id']}: {e}")

    logger.info(f"Generated embeddings for {len(embedded)} questions")

    # 4. Store in Qdrant
    qdrant_client = get_qdrant_client()
    setup_collection(qdrant_client)

    points = []
    for q, text_emb, voice_emb in embedded:
        vectors = {"text": text_emb}
        if voice_emb:
            vectors["voice_text"] = voice_emb
        else:
            vectors["voice_text"] = [0.0] * config.EMBEDDING_DIMENSION

        # Hash question_id to get a stable numeric point ID
        point_id = int(hashlib.sha256(q["question_id"].encode()).hexdigest()[:16], 16)

        points.append(PointStruct(
            id=point_id,
            vector=vectors,
            payload=build_payload(q),
        ))

    # Upsert in batches of 10 to avoid timeout on Qdrant Cloud
    batch_size = 10
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        qdrant_client.upsert(
            collection_name=config.QDRANT_COLLECTION,
            points=batch,
        )
        logger.info(f"  Upserted batch {i // batch_size + 1}: {len(batch)} points")

    logger.info(f"Stored {len(points)} questions in '{config.QDRANT_COLLECTION}'")

    # Close qdrant client to release the file lock (important for local storage)
    qdrant_client.close()

    # 5. Summary
    phases = set(q["phase"] for q, _, _ in embedded)
    concepts = set(q["concept_id"] for q, _, _ in embedded)
    difficulties = set(q["difficulty"] for q, _, _ in embedded)

    logger.info("--- Ingestion Summary ---")
    logger.info(f"  Total loaded: {len(questions)}")
    logger.info(f"  Embedded & stored: {len(embedded)}")
    logger.info(f"  Concepts: {sorted(concepts)}")
    logger.info(f"  Phases: {sorted(phases)}")
    logger.info(f"  Difficulties: {sorted(difficulties)}")
    logger.info("--- Done ---")


if __name__ == "__main__":
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_bank.json")
    input_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    ingest(input_path)
