"""
FastAPI server for AD-401 -- Visual Cue Retrieval Engine.

Provides POST /visual-cue/retrieve endpoint.
Queries Qdrant to return the most relevant visual cue
for a given concept, error type, and difficulty.

Usage:
    pip install -r requirements.txt
    python server.py

Then call:
    POST http://localhost:8003/visual-cue/retrieve
"""

import os
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from qdrant_client import QdrantClient

import config
from models import (
    VisualCueRetrieveRequest, VisualCueRetrieveResponse,
    VisualCueNotFoundResponse,
)
from visual_cue_service import get_visual_cue, count_available_cues

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
    title="Nablix Math Tutor - Visual Cue Retrieval API",
    description="POST /visual-cue/retrieve -- returns most relevant visual cue for an error type",
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
        has_cues = config.QDRANT_COLLECTION in collections
        return {
            "status": "ok",
            "qdrant_cloud": bool(config.QDRANT_URL),
            "collection_exists": has_cues,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/visual-cue/retrieve", response_model=VisualCueRetrieveResponse)
def retrieve_visual_cue(body: VisualCueRetrieveRequest):
    """
    Return the most relevant visual cue for the given error type and concept.

    The AI tutor calls this when it decides a visual aid would help
    the student understand their mistake. The response includes a
    visual_cue_type that tells Manav's frontend what kind of visual
    component to render, and a text description of the visual.
    """
    try:
        result = get_visual_cue(
            concept_id=body.concept_id,
            error_type=body.error_type,
            difficulty=body.difficulty.value,
            exclude_content_ids=body.exclude_content_ids,
            qdrant_client=qdrant_client,
            openai_client=openai_client,
        )

        if result is None:
            total = count_available_cues(
                concept_id=body.concept_id,
                error_type=body.error_type,
                difficulty=body.difficulty.value,
                qdrant_client=qdrant_client,
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "No visual cue found for this concept/error_type/difficulty.",
                    "concept_id": body.concept_id,
                    "error_type": body.error_type,
                    "difficulty": body.difficulty.value,
                    "total_cues": total,
                    "excluded": len(body.exclude_content_ids),
                },
            )

        return VisualCueRetrieveResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Visual cue retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8003"))
    logger.info(f"Starting visual cue server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
