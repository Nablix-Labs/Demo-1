import os
import logging

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

@app.get("/health")
def health_check():
    return {"status": "ok", "qdrant_cloud": bool(config.QDRANT_URL)}

@app.post("/retrieve")
def retrieve_endpoint(body: RetrievalRequestBody):
    try:
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
        return response_to_dict(response)

    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
