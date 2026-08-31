"""Shared test fixtures.

Local `.env` values may point adapters at live services. This autouse fixture
forces mock mode for ordinary route tests, making the suite independent of
machine-specific service settings.

`test_vision_provider.py` is unaffected: it calls `_build_vision_adapter` with
explicit settings and monkeypatches `httpx`, so it still exercises the real
adapter path without leaving the process.
"""

import os

# Both of these must land before the first app import.
#
# 1. Settings binds its env-file source at class-creation time.
# 2. Four modules (voice/core, rag/*) call load_dotenv() at import, which
#    copies the whole deployment .env into os.environ -- at which point
#    Settings reads the values as ordinary environment variables and
#    env_file is irrelevant. Neutering it here is the only single place
#    that covers all four.
#
# A suite that picks up real service URLs and API keys stops testing this
# code and starts testing someone else's uptime and billing.
os.environ["NABLIX_ENV_FILE"] = ""

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

from collections.abc import Iterator

import pytest

from app.adapters import provider
from app.core.config import Settings, get_settings
from app.models.session import SessionRecord
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


async def _skip_session_persistence(_: SessionRecord) -> None:
    """Keep unit tests independent from the production PostgreSQL service."""


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
        # Several tests borrow helpers across modules and start a session by
        # concept_id. Without a mapping here they only passed because the
        # deployment .env leaked one in.
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
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
    monkeypatch.setattr(session_service, "get_settings", lambda: test_settings)
    monkeypatch.setattr(session_service, "save_session", _skip_session_persistence)
    yield
    get_settings.cache_clear()
