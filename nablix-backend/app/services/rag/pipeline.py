import json
import os
import sys
import logging
import hashlib
from datetime import datetime, timezone

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    PayloadSchemaType,
)

from validators import validate_batch, ContentItem
from guardrail import check_content_item
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingestion")

def get_embedding(client: OpenAI, text: str) -> list[float]:
    response = client.embeddings.create(
        input=text,
        model=config.EMBEDDING_MODEL,
    )
    return response.data[0].embedding

def setup_qdrant(client: QdrantClient):
    collections = [c.name for c in client.get_collections().collections]

    if config.QDRANT_COLLECTION in collections:
        logger.info(f"Collection '{config.QDRANT_COLLECTION}' already exists, skipping creation.")
        _create_payload_indexes(client)
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
    logger.info(f"Created collection '{config.QDRANT_COLLECTION}' with named vectors: text, voice_text")

    _create_payload_indexes(client)

def _create_payload_indexes(client: QdrantClient):
    index_fields = {
        "approval_status": PayloadSchemaType.KEYWORD,
        "concept_id": PayloadSchemaType.KEYWORD,
        "content_type": PayloadSchemaType.KEYWORD,
        "error_type": PayloadSchemaType.KEYWORD,
        "difficulty": PayloadSchemaType.KEYWORD,
        "hint_level": PayloadSchemaType.INTEGER,
    }

    for field_name, field_type in index_fields.items():
        try:
            client.create_payload_index(
                collection_name=config.QDRANT_COLLECTION,
                field_name=field_name,
                field_schema=field_type,
            )
            logger.info(f"  Created index: {field_name} ({field_type})")
        except Exception as e:
            logger.info(f"  Index {field_name}: already exists or skipped ({e})")

def build_payload(item: ContentItem) -> dict:
    return {
        "content_id": item.content_id,
        "concept_id": item.concept_id,
        "topic": item.topic,
        "subtopic": item.subtopic,
        "content_type": item.content_type.value,
        "difficulty": item.difficulty.value,
        "age_band": item.age_band,
        "language": item.language,
        "delivery_format": [d.value for d in item.delivery_format],
        "text": item.text,
        "voice_text": item.voice_text,
        "error_type": item.error_type.value if item.error_type else None,
        "hint_level": item.hint_level,
        "step_number": item.step_number,
        "diagnostic_purpose": item.diagnostic_purpose,
        "expected_answer": item.expected_answer,
        "expected_method": item.expected_method,
        "visual_cue_type": item.visual_cue_type.value if item.visual_cue_type else None,
        "operation_type": item.operation_type.value if item.operation_type else None,
        "version": item.version,
        "approval_status": item.approval_status.value,
        "created_by": item.created_by,
        "approved_by": item.approved_by,
        "approved_date": item.approved_date,
    }

def ingest(input_path: str):

    logger.info(f"Reading content from: {input_path}")
    with open(input_path) as f:
        raw_items = json.load(f)
    logger.info(f"Loaded {len(raw_items)} items")

    logger.info("Validating items against schema...")
    valid_items, errors = validate_batch(raw_items)

    if errors:
        logger.warning(f"{len(errors)} items failed validation:")
        for err in errors:
            logger.warning(f"  {err['content_id']}: {err['error']}")

    logger.info(f"{len(valid_items)} items passed validation")

    if not valid_items:
        logger.error("No valid items to ingest. Exiting.")
        return

    approved_items = [item for item in valid_items if item.approval_status.value == "APPROVED"]
    skipped = len(valid_items) - len(approved_items)
    if skipped > 0:
        logger.info(f"Skipped {skipped} non-APPROVED items (only APPROVED items get ingested)")
    logger.info(f"{len(approved_items)} APPROVED items to ingest")

    if not approved_items:
        logger.info("No APPROVED items to ingest. Done.")
        return

    logger.info(f"Generating embeddings using model: {config.EMBEDDING_MODEL}")
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

    embedded_items = []
    for item in approved_items:
        try:
            text_embedding = get_embedding(openai_client, item.text)
            voice_embedding = None
            if item.voice_text:
                voice_embedding = get_embedding(openai_client, item.voice_text)
            embedded_items.append((item, text_embedding, voice_embedding))
            logger.info(f"  Embedded: {item.content_id}")
        except Exception as e:
            logger.error(f"  Failed to embed {item.content_id}: {e}")

    logger.info(f"Generated embeddings for {len(embedded_items)} items")

    if config.QDRANT_URL and config.QDRANT_API_KEY:
        logger.info(f"Connecting to Qdrant Cloud at: {config.QDRANT_URL}")
        qdrant_client = QdrantClient(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY,
        )
    else:
        qdrant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
        logger.info(f"Using local Qdrant storage at: {qdrant_path}")
        qdrant_client = QdrantClient(path=qdrant_path)
    setup_qdrant(qdrant_client)

    points = []
    for item, text_emb, voice_emb in embedded_items:
        vectors = {"text": text_emb}
        if voice_emb:
            vectors["voice_text"] = voice_emb
        else:
            vectors["voice_text"] = [0.0] * config.EMBEDDING_DIMENSION

        point_id = int(hashlib.sha256(item.content_id.encode()).hexdigest()[:16], 16)

        point = PointStruct(
            id=point_id,
            vector=vectors,
            payload=build_payload(item),
        )
        points.append(point)

    qdrant_client.upsert(
        collection_name=config.QDRANT_COLLECTION,
        points=points,
    )
    logger.info(f"Stored {len(points)} items in Qdrant collection '{config.QDRANT_COLLECTION}'")

    for item, _, _ in embedded_items:
        logger.info(
            f"  INGESTED: content_id={item.content_id}, "
            f"timestamp={datetime.now(timezone.utc).isoformat()}, "
            f"model={config.EMBEDDING_MODEL}"
        )

    answers_by_concept: dict[str, list[str]] = {}
    for item, _, _ in embedded_items:
        if item.expected_answer:
            answers_by_concept.setdefault(item.concept_id, []).append(item.expected_answer)

    flagged = []
    for item, _, _ in embedded_items:
        related_answers = answers_by_concept.get(item.concept_id, [])
        passed, reason = check_content_item(
            content_id=item.content_id,
            content_type=item.content_type.value,
            text=item.text,
            voice_text=item.voice_text,
            expected_answer=item.expected_answer,
            related_answers=related_answers,
        )
        if not passed:
            flagged.append((item.content_id, reason))
            logger.warning(f"  GUARDRAIL FLAGGED: {item.content_id} — {reason}")

    if flagged:
        logger.warning(f"{len(flagged)} items flagged by guardrail — would be set to REJECTED")
    else:
        logger.info("All items passed guardrail check")

    logger.info("--- Ingestion Summary ---")
    logger.info(f"  Total items read: {len(raw_items)}")
    logger.info(f"  Validation errors: {len(errors)}")
    logger.info(f"  Non-APPROVED skipped: {skipped}")
    logger.info(f"  Embedded & stored: {len(embedded_items)}")
    logger.info(f"  Guardrail flagged: {len(flagged)}")
    logger.info("--- Done ---")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <path_to_content.json>")
        sys.exit(1)

    ingest(sys.argv[1])
