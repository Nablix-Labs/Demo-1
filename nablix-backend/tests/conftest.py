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

from app.adapters import provider, rag_service
from app.core.config import Settings, get_settings
from app.models.rag import (
    RAGQueryMetadata,
    RAGRetrieveRequest,
    RAGRetrieveResponse,
    RAGRetrievedContent,
)
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

    async def fake_fetch_question(
        concept_id: str,
        phase: str,
        exclude_question_ids: list[str] | None,
        difficulty: str,
    ) -> tuple[str, str, str] | None:
        del concept_id, difficulty
        question = _TEST_QUESTIONS[phase]
        if question[2] in set(exclude_question_ids or []):
            return None
        return question

    def fake_retrieve_content(
        request: RAGRetrieveRequest,
        settings: Settings,
    ) -> RAGRetrieveResponse:
        del settings
        result = RAGRetrievedContent(
            content_id="TEST_HINT_001",
            content_type="HINT",
            hint_level=request.hint_level,
            text="Check the inverse operation before simplifying.",
            voice_text=None,
            relevance_score=0.91,
            concept_id="mock_curriculum",
            error_type=request.error_type,
            difficulty=request.difficulty,
            version="test",
            approval_status="APPROVED",
        )
        return RAGRetrieveResponse(
            query_id=request.query_id,
            results=[result],
            result_count=1,
            fallback_used=False,
            query_metadata=RAGQueryMetadata(
                retrieval_time_ms=1,
                filters_applied=[],
            ),
        )

    monkeypatch.setattr(
        provider,
        "get_settings",
        lambda: test_settings,
    )
    monkeypatch.setattr(session_service, "fetch_question", fake_fetch_question)
    monkeypatch.setattr(rag_service, "retrieve_content", fake_retrieve_content)
    yield
    get_settings.cache_clear()
