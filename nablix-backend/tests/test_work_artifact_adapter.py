import asyncio

import pytest

from app.adapters import student_model
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.work_artifact import WorkArtifactPersistRequest


def _settings() -> Settings:
    return Settings(
        student_model_url="https://student-model.example/",
        student_model_topic_ids={},
        use_mock_student_model=False,
    )


def _request() -> WorkArtifactPersistRequest:
    return WorkArtifactPersistRequest(
        student_id="ST003",
        topic_id="ALG-KS3-01",
        question_id="Q-T01-005",
        question_usage_id="QU-T01-005-P3",
        page_count=2,
        combined_pdf_base64="JVBERi0=",
        per_page_ocr_text=["t + 3", "so t + 3"],
        combined_ocr_text="t + 3\nso t + 3",
    )


def test_persist_work_artifact_posts_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def post_json(
        name: str,
        url: str,
        body: dict[str, object],
        headers: dict[str, str],
        timeout: int,
        retries: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["body"] = body
        captured["headers"] = headers
        return {
            "artifact_id": "ART-P3-000124",
            "pdf_url": "https://blob.example/submission.pdf",
            "page_count": 2,
        }

    monkeypatch.setattr(student_model, "post_json", post_json)
    adapter = student_model.StudentModelServiceAdapter(_settings())

    result = asyncio.run(adapter.persist_work_artifact(_request(), "test-token"))

    assert result.artifact_id == "ART-P3-000124"
    assert result.pdf_url == "https://blob.example/submission.pdf"
    # Trailing slash on the configured base URL must not double up.
    assert captured["url"] == "https://student-model.example/work-artifacts"
    assert captured["headers"] == {"Authorization": "Bearer test-token"}
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["question_usage_id"] == "QU-T01-005-P3"
    assert body["per_page_ocr_text"] == ["t + 3", "so t + 3"]


def test_persist_work_artifact_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def post_json(*args: object, **kwargs: object) -> dict[str, object]:
        return {"pdf_url": "https://blob.example/submission.pdf"}

    monkeypatch.setattr(student_model, "post_json", post_json)
    adapter = student_model.StudentModelServiceAdapter(_settings())

    with pytest.raises(AdapterError):
        asyncio.run(adapter.persist_work_artifact(_request(), "test-token"))


def test_persist_work_artifact_requires_configured_url() -> None:
    adapter = student_model.MockStudentModelAdapter()

    with pytest.raises(AdapterError):
        asyncio.run(adapter.persist_work_artifact(_request(), "test-token"))
