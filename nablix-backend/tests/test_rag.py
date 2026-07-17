from types import SimpleNamespace

import httpx
import pytest
from qdrant_client import models

from app.adapters.rag_service import RAGServiceAdapterClient
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext
from app.models.rag import RAGRetrieveRequest
from app.services import rag_retrieval


_REQUEST_BODY: dict[str, object] = {
    "query_id": "query-1",
    "concept_id": "ALG_LINEAR_ONE_STEP",
    "content_type": "HINT",
    "hint_level": 1,
    "error_type": "SIGN_ERROR",
    "difficulty": "FOUNDATION",
    "input_source": "TEXT",
    "max_results": 3,
    "exclude_content_ids": [],
}


def test_internal_adapter_resolves_guardrail_hint_level() -> None:
    context = AdapterContext(
        session_id="SESSION001",
        student_id="ST001",
        message="I am stuck",
        attempt_count=2,
        concept_id="ALG_LINEAR_ONE_STEP",
    )

    payload = RAGServiceAdapterClient(Settings())._build_retrieve_payload(
        context,
        "UNKNOWN_ERROR",
        None,
    )

    assert payload["hint_level"] == 2


def test_retrieve_content_queries_shared_qdrant_with_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, models.Filter, int]] = []

    class FakeEmbeddings:
        def create(self, *, model: str, input: str) -> SimpleNamespace:
            assert model == "text-embedding-3-small"
            assert "ALG_LINEAR_ONE_STEP_ADDITION" in input
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])

    class FakeOpenAI:
        def __init__(
            self,
            *,
            api_key: str,
            timeout: int,
            max_retries: int,
        ) -> None:
            assert api_key == "test-openai-key"
            assert timeout == 20
            # Embedding retries are the SDK's job now.
            assert max_retries == 2
            self.embeddings = FakeEmbeddings()

    class FakeQdrantClient:
        def __init__(self, *, url: str, api_key: str, timeout: int) -> None:
            assert url == "https://qdrant.test"
            assert api_key == "test-qdrant-key"
            assert timeout == 20

        def query_points(
            self,
            *,
            collection_name: str,
            query: list[float],
            using: str,
            query_filter: models.Filter,
            limit: int,
            with_payload: bool,
        ) -> SimpleNamespace:
            del query, with_payload
            calls.append((collection_name, using, query_filter, limit))
            if len(calls) == 1:
                request = httpx.Request("POST", "https://qdrant.test/points/query")
                raise httpx.ConnectError("temporary connection failure", request=request)
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id="point-skipped",
                        score=0.99,
                        payload={
                            "content_id": "SKIP_001",
                            "content_type": "HINT",
                            "hint_level": 1,
                            "text": "Excluded content.",
                            "voice_text": None,
                            "concept_id": "ALG_LINEAR_ONE_STEP_ADDITION",
                            "error_type": "SIGN_ERROR",
                            "difficulty": "FOUNDATION",
                            "version": "1",
                            "approval_status": "APPROVED",
                        },
                    ),
                    SimpleNamespace(
                        id="point-1",
                        score=0.93,
                        payload={
                            "content_id": "HINT_001",
                            "content_type": "HINT",
                            "hint_level": 1,
                            "text": "Undo the addition first.",
                            "voice_text": "Undo the addition first.",
                            "concept_id": "ALG_LINEAR_ONE_STEP_ADDITION",
                            "error_type": "SIGN_ERROR",
                            "difficulty": "FOUNDATION",
                            "version": "1",
                            "approval_status": "APPROVED",
                        },
                    )
                ]
            )

    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("NABLIX_QDRANT_URL", "https://qdrant.test")
    monkeypatch.setenv("NABLIX_QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv(
        "NABLIX_QDRANT_CONCEPT_ID_MAP",
        '{"ALG_LINEAR_ONE_STEP":"ALG_LINEAR_ONE_STEP_ADDITION"}',
    )
    get_settings.cache_clear()
    monkeypatch.setattr(rag_retrieval, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(rag_retrieval, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(rag_retrieval, "_clients", None)
    request = RAGRetrieveRequest.model_validate(
        {**_REQUEST_BODY, "exclude_content_ids": ["SKIP_001"]}
    )

    response = rag_retrieval.retrieve_content(request, get_settings())

    assert len(calls) == 2
    assert calls[1][0] == "math_tutor_content"
    assert calls[1][1] == "text"
    assert calls[1][3] == 4
    filter_fields: set[str] = {
        condition.key
        for condition in calls[1][2].must or []
        if isinstance(condition, models.FieldCondition)
    }
    assert filter_fields == {
        "concept_id",
        "content_type",
        "difficulty",
        "approval_status",
        "error_type",
        "hint_level",
    }
    assert response.result_count == 1
    assert response.results[0].content_id == "HINT_001"
    assert response.fallback_used is False


def test_retrieve_content_returns_empty_without_mock_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEmbeddings:
        def create(self, *, model: str, input: str) -> SimpleNamespace:
            del model, input
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])

    class FakeOpenAI:
        def __init__(
            self,
            *,
            api_key: str,
            timeout: int,
            max_retries: int,
        ) -> None:
            del api_key, timeout, max_retries
            self.embeddings = FakeEmbeddings()

    class FakeQdrantClient:
        def __init__(self, *, url: str, api_key: str, timeout: int) -> None:
            del url, api_key, timeout

        def query_points(
            self,
            *,
            collection_name: str,
            query: list[float],
            using: str,
            query_filter: models.Filter,
            limit: int,
            with_payload: bool,
        ) -> SimpleNamespace:
            del collection_name, query, using, query_filter, limit, with_payload
            return SimpleNamespace(points=[])

    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("NABLIX_QDRANT_URL", "https://qdrant.test")
    monkeypatch.setenv("NABLIX_QDRANT_API_KEY", "test-qdrant-key")
    get_settings.cache_clear()
    monkeypatch.setattr(rag_retrieval, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(rag_retrieval, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(rag_retrieval, "_clients", None)

    response = rag_retrieval.retrieve_content(
        RAGRetrieveRequest.model_validate(_REQUEST_BODY),
        get_settings(),
    )

    assert response.results == []
    assert response.result_count == 0
    assert response.fallback_used is True


def test_retrieve_content_requires_external_service_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "")
    monkeypatch.setenv("NABLIX_QDRANT_URL", "")
    monkeypatch.setenv("NABLIX_QDRANT_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(AdapterError) as raised:
        rag_retrieval.retrieve_content(
            RAGRetrieveRequest.model_validate(_REQUEST_BODY),
            get_settings(),
        )

    assert raised.value.status_code == 503
    assert "NABLIX_OPENAI_API_KEY" in str(raised.value.detail)
    assert "NABLIX_QDRANT_URL" in str(raised.value.detail)
