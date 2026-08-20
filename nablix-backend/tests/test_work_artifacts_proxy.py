"""GET /work-artifacts/{artifact_id}/pdf -- the nablix-backend proxy to
Student Model's stored PDF (mathtutor-student PR #9)."""

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.core.config import Settings
from app.core.exceptions import AdapterRequestRejected
from app.main import app

client = TestClient(app)


def _use_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        student_model_url="https://student-model.test",
        use_mock_student_model=False,
    )
    monkeypatch.setattr(provider, "get_settings", lambda: settings)


def test_forwards_the_callers_own_token_and_streams_the_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch)
    seen: dict[str, object] = {}

    async def fake_get_bytes(adapter_name, url, headers, timeout_seconds, retry_count):
        seen["url"] = url
        seen["headers"] = headers
        return b"%PDF-1.4 fake", "application/pdf"

    monkeypatch.setattr(student_model, "get_bytes", fake_get_bytes)

    response = client.get(
        "/work-artifacts/ART-42/pdf",
        headers={"Authorization": "Bearer this-students-own-token"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 fake"
    assert seen["url"] == "https://student-model.test/work-artifacts/ART-42/pdf"
    # The caller's own bearer, forwarded verbatim -- never a service token.
    assert seen["headers"] == {"Authorization": "Bearer this-students-own-token"}


def test_a_downstream_404_does_not_leak_the_internal_url_or_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch)

    async def reject(*args: object, **kwargs: object) -> None:
        raise AdapterRequestRejected(
            "student_model",
            "https://student-model.test/work-artifacts/ART-999/pdf",
            404,
            '{"error_code":"NOT_FOUND","message":"Work artifact not found."}',
            {},
        )

    monkeypatch.setattr(student_model, "get_bytes", reject)

    response = client.get(
        "/work-artifacts/ART-999/pdf",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "NOT_FOUND"
    assert "student-model.test" not in body["message"]
    assert "ART-999" in body["message"]


def test_a_downstream_5xx_keeps_the_existing_failure_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_settings(monkeypatch)

    async def fail(*args: object, **kwargs: object) -> None:
        raise AdapterRequestRejected(
            "student_model",
            "https://student-model.test/work-artifacts/ART-1/pdf",
            401,
            '{"error_code":"INVALID_TOKEN"}',
            {},
        )

    monkeypatch.setattr(student_model, "get_bytes", fail)

    response = client.get(
        "/work-artifacts/ART-1/pdf",
        headers={"Authorization": "Bearer expired"},
    )

    # Non-404 rejections are not this route's concern to sanitize -- they
    # propagate as AdapterRequestRejected already does everywhere else.
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTHENTICATION_FAILED"
