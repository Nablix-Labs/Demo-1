from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Nablix AI Math Tutor API"
    app_version: str = "1.0.0"
    debug: bool = False #Why false?

    #Service URL's
    tutor_engine_url: str = "http://localhost:8001"
    rag_service_url: str = "http://localhost:8002" #aditya
    student_model_url: str = "http://localhost:8003" #tamil
    voice_service_url: str = "http://localhost:8004" #chiru+aditya
    safety_service_url: str = "http://localhost:8004" #manjusha
    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://nablix-labs.github.io",
    ]

    #API Keys
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    vision_api_key: str = ""

    #Mock flags - True during sprint
    use_mock_tutor: bool = True
    use_mock_rag: bool = True
    use_mock_student_model: bool = True
    use_mock_voice: bool = True
    use_mock_vision: bool = True

    #Vision OCR (used when use_mock_vision is False)
    openai_vision_model: str = "gpt-5.4-mini"
    use_openai_ai_engine: bool = False
    openai_ai_engine_model: str = "gpt-4o-mini"
    openai_request_timeout_seconds: int = 20
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
    mock_session_id: str = "SESSION001"

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
