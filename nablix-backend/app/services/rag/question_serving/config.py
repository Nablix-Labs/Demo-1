"""
Config for AD-300 — Question Serving Module.
Reads from environment variables, falls back to defaults.
Same pattern as knowledge-base/ingestion/config.py.
"""

import os
from dotenv import load_dotenv

_this_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_this_dir, ".env")
_loaded = load_dotenv(_env_path)
if not _loaded:
    load_dotenv()

# OpenAI (for generating embeddings)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1536"))

# Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "math_tutor_questions")

# Qdrant Cloud (takes priority over QDRANT_HOST/PORT if set)
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
