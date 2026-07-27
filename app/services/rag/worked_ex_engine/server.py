"""
FastAPI server for AD-402 -- Worked Example Retrieval Engine.

Provides POST /worked-example/retrieve endpoint.
Queries Qdrant to return the most relevant worked example
for a given concept and operation type. Applies different-numbers
check and guardrail before returning.

Usage:
    pip install -r requirements.txt
    python server.py

Then call:
    POST http://localhost:8005/worked-example/retrieve
"""

import os
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from qdrant_client import QdrantClient

import config
from models import (
    WorkedExampleRetrieveRequest, WorkedExampleRetrieveResponse,
    WorkedExampleNotFoundResponse,
)
from worked_example_service import get_worked_example, count_available_examples

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("server")


# --- Create clients once at startup ---

openai_client = OpenAI(api_key=config.OPENAI_API_KEY)

if config.QDRANT_URL and config.QDRANT_API_KEY:
    logger.info(f"Connecting to Qdrant Cloud at: {config.QDRANT_URL}")
    qdrant_client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY, timeout=60)
else:
    qdrant_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qdrant_data")
    logger.info(f"Using local Qdrant at: {qdrant_path}")
    qdrant_client = QdrantClient(path=qdrant_path)


# --- FastAPI app ---

app = FastAPI(
    title="Nablix Math Tutor - Worked Example Retrieval API",
    description="POST /worked-example/retrieve -- returns a step-by-step worked example with different numbers",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Check if the server and Qdrant connection are working."""
    try:
        collections = [c.name for c in qdrant_client.get_collections().collections]
        has_examples = config.QDRANT_COLLECTION in collections
        return {
            "status": "ok",
            "qdrant_cloud": bool(config.QDRANT_URL),
            "collection_exists": has_examples,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/worked-example/retrieve", response_model=WorkedExampleRetrieveResponse)
def retrieve_worked_example(body: WorkedExampleRetrieveRequest):
    """
    Return a worked example for the given concept and operation type.

    The example will:
    1. Use completely different numbers from the student's current question
    2. Not reveal the student's current answer (checked by guardrail)
    3. Be marked with different_numbers_confirmed=True

    If no suitable example is found (all candidates fail the safety checks
    or none exist for this filter), returns 404.
    """
    try:
        result = get_worked_example(
            concept_id=body.concept_id,
            operation_type=body.operation_type,
            current_question=body.current_question,
            current_answer=body.current_answer,
            difficulty=body.difficulty.value,
            exclude_content_ids=body.exclude_content_ids,
            qdrant_client=qdrant_client,
            openai_client=openai_client,
        )

        if result is None:
            total = count_available_examples(
                concept_id=body.concept_id,
                operation_type=body.operation_type,
                difficulty=body.difficulty.value,
                qdrant_client=qdrant_client,
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No worked example found that passes safety checks.",
                    "concept_id": body.concept_id,
                    "operation_type": body.operation_type,
                    "difficulty": body.difficulty.value,
                    "total_examples_in_bank": total,
                    "excluded": len(body.exclude_content_ids),
                    "note": "All candidates either share numbers with the current question or reveal the answer.",
                },
            )

        return WorkedExampleRetrieveResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Worked example retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8005"))
    logger.info(f"Starting worked example server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
