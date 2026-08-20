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
        submission_id="TURN-ST003-CANVAS-1",
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
    # Idempotency key, so a retried request does not store a second artifact.
    assert body["submission_id"] == "TURN-ST003-CANVAS-1"


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


def test_fetch_topic_event_history_parses_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        return {
            "topic_id": "ALG-KS3-01",
            "student_id": "ST003",
            "topic_info": {"title": "General rules"},
            "whole_topic_evidence": {"hint_count": 2},
            "attempts": [
                {
                    "attempt_id": "ATTEMPT-021",
                    "question_id": "Q-T01-005",
                    "question_usage_id": "QU-T01-005-P3",
                    "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                    "evaluation": "INCORRECT",
                    "attempted_at": "2026-08-17T10:15:23Z",
                    "question_text": "A temperature starts at t and falls by 3.",
                    "canonical_answer": "t - 3",
                    "answer_steps": ["Identify t.", "Subtract 3."],
                    "detected_errors": [
                        {
                            "error_code": "ERR-DIRECTION-REVERSED",
                            "micro_skill_id": "T01.M3",
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(student_model, "post_json", post_json)
    adapter = student_model.StudentModelServiceAdapter(_settings())

    history = asyncio.run(
        adapter.fetch_topic_event_history("ST003", "ALG-KS3-01", "test-token")
    )

    assert captured["url"] == "https://student-model.example/topic/event-history"
    assert captured["body"] == {"student_id": "ST003", "topic_id": "ALG-KS3-01"}
    assert len(history.attempts) == 1
    attempt = history.attempts[0]
    assert attempt.is_wrong is True
    assert attempt.detected_errors[0].error_code == "ERR-DIRECTION-REVERSED"
    assert attempt.answer_steps == ["Identify t.", "Subtract 3."]


def test_fetch_topic_event_history_accepts_missing_micro_skill_and_usage_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The service omits these for real, ordinary reasons — not malformed data.

    An error that isn't tied to a specific skill has no micro_skill_id; some
    attempts have no question_usage_id. Previously this failed the WHOLE
    response parse (one bad attempt took down every attempt in the topic).
    """

    async def post_json(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "topic_id": "ALG-KS3-01",
            "student_id": "ST003",
            "topic_info": {"title": "General rules"},
            "attempts": [
                {
                    "attempt_id": "ATTEMPT-022",
                    "question_id": "Q-T01-006",
                    # question_usage_id omitted entirely
                    "phase": "PHASE_3_INDEPENDENT_PRACTICE",
                    "evaluation": "INCORRECT",
                    "attempted_at": "2026-08-17T10:16:00Z",
                    "detected_errors": [
                        {"error_code": "ERR-UNMAPPED"}  # micro_skill_id omitted
                    ],
                }
            ],
        }

    monkeypatch.setattr(student_model, "post_json", post_json)
    adapter = student_model.StudentModelServiceAdapter(_settings())

    history = asyncio.run(
        adapter.fetch_topic_event_history("ST003", "ALG-KS3-01", "test-token")
    )

    attempt = history.attempts[0]
    assert attempt.question_usage_id is None
    assert attempt.detected_errors[0].micro_skill_id is None


def test_fetch_topic_event_history_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def post_json(*args: object, **kwargs: object) -> dict[str, object]:
        return {"student_id": "ST003"}

    monkeypatch.setattr(student_model, "post_json", post_json)
    adapter = student_model.StudentModelServiceAdapter(_settings())

    with pytest.raises(AdapterError):
        asyncio.run(
            adapter.fetch_topic_event_history("ST003", "ALG-KS3-01", "test-token")
        )
