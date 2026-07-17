"""
Ingestion script for AD-401 -- Visual Cue Bank.

Reads visual_cue_bank.json, generates embeddings via OpenAI,
stores in a separate Qdrant collection (math_tutor_visual_cues).

Usage:
    python ingest.py
    python ingest.py path/to/custom_visual_cues.json
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
logger = logging.getLogger("ingest_visual_cues")


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
    """Create the visual cues collection if it doesn't exist."""
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
        "error_type": PayloadSchemaType.KEYWORD,
        "visual_cue_type": PayloadSchemaType.KEYWORD,
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


def build_payload(cue: dict) -> dict:
    """Convert a visual cue dict to a Qdrant payload."""
    return {
        "content_id": cue["content_id"],
        "concept_id": cue["concept_id"],
        "topic": cue["topic"],
        "subtopic": cue["subtopic"],
        "error_type": cue["error_type"],
        "visual_cue_type": cue["visual_cue_type"],
        "difficulty": cue["difficulty"],
        "text": cue["text"],
        "voice_text": cue.get("voice_text"),
        "age_band": cue.get("age_band", "11-14"),
        "language": cue.get("language", "en"),
        "approval_status": cue.get("approval_status", "APPROVED"),
    }


def ingest(input_path: str):
    """Main ingestion function. Read JSON, embed, store in Qdrant."""

    # 1. Read visual cues
    logger.info(f"Reading visual cues from: {input_path}")
    with open(input_path) as f:
        cues = json.load(f)
    logger.info(f"Loaded {len(cues)} visual cues")

    # 2. Validate required fields
    required_fields = ["content_id", "concept_id", "error_type", "visual_cue_type",
                       "difficulty", "text", "topic", "subtopic"]
    valid_cues = []
    for i, c in enumerate(cues):
        missing = [f for f in required_fields if f not in c or not c[f]]
        if missing:
            logger.warning(f"Cue {i} ({c.get('content_id', '?')}): missing fields {missing}, skipping")
        else:
            valid_cues.append(c)

    logger.info(f"{len(valid_cues)} cues passed validation")

    if not valid_cues:
        logger.error("No valid visual cues to ingest.")
        return

    # 3. Generate embeddings
    logger.info(f"Generating embeddings using model: {config.EMBEDDING_MODEL}")
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

    embedded = []
    for c in valid_cues:
        try:
            text_emb = get_embedding(openai_client, c["text"])
            voice_emb = None
            if c.get("voice_text"):
                voice_emb = get_embedding(openai_client, c["voice_text"])
            embedded.append((c, text_emb, voice_emb))
            logger.info(f"  Embedded: {c['content_id']}")
        except Exception as e:
            logger.error(f"  Failed to embed {c['content_id']}: {e}")

    logger.info(f"Generated embeddings for {len(embedded)} visual cues")

    # 4. Store in Qdrant
    qdrant_client = get_qdrant_client()
    setup_collection(qdrant_client)

    points = []
    for c, text_emb, voice_emb in embedded:
        vectors = {"text": text_emb}
        if voice_emb:
            vectors["voice_text"] = voice_emb
        else:
            vectors["voice_text"] = [0.0] * config.EMBEDDING_DIMENSION

        # Hash content_id to get a stable numeric point ID
        point_id = int(hashlib.sha256(c["content_id"].encode()).hexdigest()[:16], 16)

        points.append(PointStruct(
            id=point_id,
            vector=vectors,
            payload=build_payload(c),
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

    logger.info(f"Stored {len(points)} visual cues in '{config.QDRANT_COLLECTION}'")

    # Close qdrant client to release the file lock
    qdrant_client.close()

    # 5. Summary
    error_types = set(c["error_type"] for c, _, _ in embedded)
    concepts = set(c["concept_id"] for c, _, _ in embedded)
    cue_types = set(c["visual_cue_type"] for c, _, _ in embedded)

    logger.info("--- Ingestion Summary ---")
    logger.info(f"  Total loaded: {len(cues)}")
    logger.info(f"  Embedded & stored: {len(embedded)}")
    logger.info(f"  Concepts: {sorted(concepts)}")
    logger.info(f"  Error types: {sorted(error_types)}")
    logger.info(f"  Visual cue types: {sorted(cue_types)}")
    logger.info("--- Done ---")


if __name__ == "__main__":
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visual_cue_bank.json")
    input_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    ingest(input_path)
