"""
Ingestion script for AD-402 -- Worked Example Bank.

Reads worked_example_bank.json, generates embeddings via OpenAI,
stores in a separate Qdrant collection (math_tutor_worked_examples).

Same pattern as AD-401/ingest.py but adds operation_type,
example_question, and example_answer to the payload.

Usage:
    python ingest.py
    python ingest.py path/to/custom_worked_examples.json
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
logger = logging.getLogger("ingest_worked_examples")


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
    """Create the worked examples collection if it doesn't exist."""
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
        "content_id": PayloadSchemaType.KEYWORD,
        "concept_id": PayloadSchemaType.KEYWORD,
        "operation_type": PayloadSchemaType.KEYWORD,
        "difficulty": PayloadSchemaType.KEYWORD,
        "topic": PayloadSchemaType.KEYWORD,
        "subtopic": PayloadSchemaType.KEYWORD,
        "approval_status": PayloadSchemaType.KEYWORD,
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


def build_payload(example: dict) -> dict:
    """Convert a worked example dict to a Qdrant payload.

    Compared to AD-401, this adds operation_type, example_question,
    and example_answer fields.
    """
    return {
        "content_id": example["content_id"],
        "concept_id": example["concept_id"],
        "topic": example["topic"],
        "subtopic": example["subtopic"],
        "operation_type": example["operation_type"],
        "difficulty": example["difficulty"],
        "example_question": example["example_question"],
        "example_answer": example["example_answer"],
        "text": example["text"],
        "voice_text": example.get("voice_text"),
        "age_band": example.get("age_band", "11-14"),
        "language": example.get("language", "en"),
        "approval_status": example.get("approval_status", "APPROVED"),
    }


def ingest(input_path: str):
    """Main ingestion function. Read JSON, embed, store in Qdrant."""

    # 1. Read worked examples
    logger.info(f"Reading worked examples from: {input_path}")
    with open(input_path) as f:
        examples = json.load(f)
    logger.info(f"Loaded {len(examples)} worked examples")

    # 2. Validate required fields
    required_fields = [
        "content_id", "concept_id", "operation_type", "difficulty",
        "example_question", "example_answer", "text", "topic", "subtopic",
    ]
    valid_examples = []
    for i, ex in enumerate(examples):
        missing = [f for f in required_fields if f not in ex or not ex[f]]
        if missing:
            logger.warning(f"Example {i} ({ex.get('content_id', '?')}): missing fields {missing}, skipping")
        else:
            valid_examples.append(ex)

    logger.info(f"{len(valid_examples)} examples passed validation")

    if not valid_examples:
        logger.error("No valid worked examples to ingest.")
        return

    # 3. Generate embeddings
    logger.info(f"Generating embeddings using model: {config.EMBEDDING_MODEL}")
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

    embedded = []
    for ex in valid_examples:
        try:
            text_emb = get_embedding(openai_client, ex["text"])
            voice_emb = None
            if ex.get("voice_text"):
                voice_emb = get_embedding(openai_client, ex["voice_text"])
            embedded.append((ex, text_emb, voice_emb))
            logger.info(f"  Embedded: {ex['content_id']}")
        except Exception as e:
            logger.error(f"  Failed to embed {ex['content_id']}: {e}")

    logger.info(f"Generated embeddings for {len(embedded)} worked examples")

    # 4. Store in Qdrant
    qdrant_client = get_qdrant_client()
    setup_collection(qdrant_client)

    points = []
    for ex, text_emb, voice_emb in embedded:
        vectors = {"text": text_emb}
        if voice_emb:
            vectors["voice_text"] = voice_emb
        else:
            vectors["voice_text"] = [0.0] * config.EMBEDDING_DIMENSION

        # Hash content_id to get a stable numeric point ID
        point_id = int(hashlib.sha256(ex["content_id"].encode()).hexdigest()[:16], 16)

        points.append(PointStruct(
            id=point_id,
            vector=vectors,
            payload=build_payload(ex),
        ))

    # Upsert in batches of 10
    batch_size = 10
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        qdrant_client.upsert(
            collection_name=config.QDRANT_COLLECTION,
            points=batch,
        )
        logger.info(f"  Upserted batch {i // batch_size + 1}: {len(batch)} points")

    logger.info(f"Stored {len(points)} worked examples in '{config.QDRANT_COLLECTION}'")

    # Close qdrant client to release the file lock
    qdrant_client.close()

    # 5. Summary
    operation_types = set(ex["operation_type"] for ex, _, _ in embedded)
    concepts = set(ex["concept_id"] for ex, _, _ in embedded)

    logger.info("--- Ingestion Summary ---")
    logger.info(f"  Total loaded: {len(examples)}")
    logger.info(f"  Embedded & stored: {len(embedded)}")
    logger.info(f"  Concepts: {sorted(concepts)}")
    logger.info(f"  Operation types: {sorted(operation_types)}")
    logger.info("--- Done ---")


if __name__ == "__main__":
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worked_example_bank.json")
    input_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    ingest(input_path)
