"""Shared test fixtures.

Local `.env` values may point adapters at live services. This autouse fixture
forces mock mode for ordinary route tests, making the suite independent of
machine-specific service settings.

`test_vision_provider.py` is unaffected: it calls `_build_vision_adapter` with
explicit settings and monkeypatches `httpx`, so it still exercises the real
adapter path without leaving the process.
"""

from collections.abc import Iterator

import pytest

from app.adapters import provider
from app.core.config import Settings, get_settings
from app.services import session_service


# Question text/answers come from the one demo table so they can't drift.
_PHASE_QUESTION_IDS: dict[str, str] = {
    "DIAGNOSTIC": "ALG_EQ_DIAG_001",
    "CONCEPT_ORIENTATION": "ALG_EQ_CO_001",
    "GUIDED_PRACTICE": "ALG_EQ_GP_001",
    "INDEPENDENT_PRACTICE": "ALG_EQ_IP_001",
    "REVIEW": "ALG_EQ_REV_001",
}
_TEST_QUESTIONS: dict[str, tuple[str, str, str]] = {
    phase: (
        session_service._DEMO_QUESTIONS[question_id][0],
        session_service._DEMO_QUESTIONS[question_id][1],
        question_id,
    )
    for phase, question_id in _PHASE_QUESTION_IDS.items()
}


@pytest.fixture(autouse=True)
def force_mock_adapters(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "false")
    monkeypatch.setenv("NABLIX_QDRANT_URL", "https://qdrant.test")
    monkeypatch.setenv("NABLIX_QDRANT_API_KEY", "test-key")
    get_settings.cache_clear()
    test_settings = Settings(
        student_model_url="",
        student_model_topic_ids={},
        use_mock_student_model=True,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
        qdrant_url="https://qdrant.test",
        qdrant_api_key="test-key",
    )

    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: test_settings,
    )
    yield
    get_settings.cache_clear()
