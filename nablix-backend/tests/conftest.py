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
from app.core.config import Settings


@pytest.fixture(autouse=True)
def force_mock_adapters(monkeypatch):
    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: Settings(
            use_mock_tutor=True,
            use_mock_rag=True,
            use_mock_student_model=True,
            use_mock_voice=True,
            use_mock_vision=True,
        ),
    )
