"""
FastAPI server for AD-300 — Question Serving.

Provides POST /question/next endpoint.
Queries Qdrant to return the next unseen question
for a given concept, phase, and difficulty.

Usage:
    pip install -r requirements.txt
    python server.py

Then call:
    POST http://localhost:8002/question/next
"""

import os
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from qdrant_client import QdrantClient

import config
from models import (
    QuestionNextRequest, QuestionNextResponse, QuestionNotFoundResponse,
    DiagnosticQuestionRequest, DiagnosticQuestionResponse,
)
from question_service import get_next_question, get_diagnostic_question, count_available_questions

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
    title="Nablix Math Tutor - Question Serving API",
    description="POST /question/next — returns next unseen question for a student",
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
        has_questions = config.QDRANT_COLLECTION in collections
        return {
            "status": "ok",
            "qdrant_cloud": bool(config.QDRANT_URL),
            "collection_exists": has_questions,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/question/next", response_model=QuestionNextResponse)
def next_question(body: QuestionNextRequest):
    """
    Return the next unseen question for the given concept, phase, and difficulty.

    The caller passes previously_seen_ids so the endpoint knows which
    questions to skip. If all questions for the filter have been seen,
    returns 404.
    """
    try:
        result = get_next_question(
            concept_id=body.concept_id,
            phase=body.phase.value,
            difficulty=body.difficulty.value,
            previously_seen_ids=body.previously_seen_ids,
            qdrant_client=qdrant_client,
            openai_client=openai_client,
        )

        if result is None:
            total = count_available_questions(
                concept_id=body.concept_id,
                phase=body.phase.value,
                difficulty=body.difficulty.value,
                qdrant_client=qdrant_client,
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No unseen questions available for this concept/phase/difficulty.",
                    "concept_id": body.concept_id,
                    "phase": body.phase.value,
                    "difficulty": body.difficulty.value,
                    "total_questions": total,
                    "previously_seen": len(body.previously_seen_ids),
                },
            )

        return QuestionNextResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Question retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/diagnostic/question", response_model=DiagnosticQuestionResponse)
def diagnostic_question(body: DiagnosticQuestionRequest):
    """
    Return the next unseen DIAGNOSTIC question for a concept and difficulty.

    AD-400: Diagnostic Question Bank endpoint.
    Unlike /question/next, this always filters for DIAGNOSTIC phase
    and returns extra fields (diagnostic_purpose, expected_method)
    that help the AI engine interpret the student's response.
    """
    try:
        result = get_diagnostic_question(
            concept_id=body.concept_id,
            difficulty=body.difficulty.value,
            previously_seen_ids=body.previously_seen_ids,
            qdrant_client=qdrant_client,
            openai_client=openai_client,
        )

        if result is None:
            total = count_available_questions(
                concept_id=body.concept_id,
                phase="DIAGNOSTIC",
                difficulty=body.difficulty.value,
                qdrant_client=qdrant_client,
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No unseen diagnostic questions available for this concept/difficulty.",
                    "concept_id": body.concept_id,
                    "difficulty": body.difficulty.value,
                    "total_questions": total,
                    "previously_seen": len(body.previously_seen_ids),
                },
            )

        return DiagnosticQuestionResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Diagnostic question retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    logger.info(f"Starting question server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
