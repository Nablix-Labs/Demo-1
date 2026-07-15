"""Shared test fixtures.

Local `.env` values may point adapters at live services. This autouse fixture
forces mock mode for ordinary route tests, making the suite independent of
machine-specific service settings.

`test_vision_provider.py` is unaffected: it calls `_build_vision_adapter` with
explicit settings and monkeypatches `httpx`, so it still exercises the real
adapter path without leaving the process.
"""

import pytest

from app.adapters import provider
from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def force_mock_adapters(monkeypatch):
    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "false")
    get_settings.cache_clear()
    test_settings = Settings(
        student_model_url="",
        student_model_topic_ids={},
        use_mock_student_model=True,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
    )
    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: test_settings,
    )
    yield
    get_settings.cache_clear()
