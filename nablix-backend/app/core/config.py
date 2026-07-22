from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Nablix AI Math Tutor API"
    app_version: str = "1.0.0"

    # External service URLs
    tutor_engine_url: str = "http://localhost:8001"
    voice_service_url: str = "http://localhost:8004" #chiru+aditya
    safety_service_url: str = "http://localhost:8004" #manjusha
    student_model_url: str = ""
    student_model_topic_ids: dict[str, int] = Field(default_factory=dict)
    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://nablix-labs.github.io",
    ]

    #API Keys
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    vision_api_key: str = ""

    # Shared Qdrant Cloud collection used by question selection and RAG retrieval
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    # Hint/curriculum content (RAG retrieval) vs question bank: two collections.
    qdrant_collection: str = "math_tutor_content"
    qdrant_questions_collection: str = "math_tutor_questions"
    # Backend concept ids -> knowledge-base concept ids (e.g. ALG_LINEAR_ONE_STEP
    # -> ALG_LINEAR_ONE_STEP_ADDITION), same pattern as student_model_topic_ids.
    qdrant_concept_id_map: dict[str, str] = Field(default_factory=dict)

    #Mock flags - True during sprint
    # (the tutor has no flag: it always runs the in-process AI Engine)
    use_mock_tutor: bool = True
    use_mock_student_model: bool = False
    use_mock_voice: bool = True
    use_mock_vision: bool = True

    #Vision OCR (used when use_mock_vision is False)
    ocr_provider: Literal["openai", "mathpix"] = "openai"
    openai_vision_model: str = "gpt-5.4-mini"
    mathpix_app_id: str = ""
    mathpix_app_key: str = ""
    use_openai_ai_engine: bool = False
    openai_ai_engine_model: str = "gpt-4o-mini"
    openai_request_timeout_seconds: int = 20
    openai_prompt_cache_key_enabled: bool = False
    adapter_request_timeout_seconds: int = 20
    adapter_request_retry_count: int = 2

    #Validation
    max_text_input_length: int = 500
    min_voice_confidence_threshold: float = 0.7
    min_ocr_confidence_threshold: float = 0.75
    max_snapshot_bytes: int = 2_000_000

    #ID format patterns(SIMPLE REGEX FOR PATTERN MATCHING)
    student_id_pattern: str = r"^ST\d{3}$"
    session_id_pattern: str = r"^SESSION\d{3}$"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NABLIX_",
        extra="ignore",
    )


# Least REcently Used (LRU) cache to store the result of a function
@lru_cache()
def get_settings() -> Settings:
    return Settings()
