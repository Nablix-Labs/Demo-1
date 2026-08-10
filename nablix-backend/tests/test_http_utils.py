import asyncio

import httpx
import pytest

from app.adapters import http_utils, student_model
from app.core.config import Settings
from app.core.exceptions import (
    AdapterRequestRejected,
    JourneyVersionConflict,
)
from app.models.student_model_session import SessionOpenedEvent


def test_post_json_does_not_retry_rejected_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class FakeAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                401,
                json={"error_code": "INVALID_TOKEN"},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(http_utils.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(AdapterRequestRejected) as error:
        asyncio.run(
            http_utils.post_json(
                "student_model",
                "https://student-model.example/interaction",
                {"topic_id": 2},
                {"Authorization": "Bearer invalid"},
                20,
                2,
            )
        )

    assert calls == 1
    assert error.value.status_code == 401


def test_student_model_adapter_surfaces_journey_version_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_stale_event(*args: object) -> dict[str, object]:
        del args
        raise AdapterRequestRejected(
            "student_model",
            "https://student-model.example/session/event",
            409,
            '{"error_code":"JOURNEY_VERSION_CONFLICT","journey_state":{"version":4}}',
            {"expected_journey_version": 3},
        )

    monkeypatch.setattr(student_model, "post_json", reject_stale_event)
    adapter = student_model.StudentModelServiceAdapter(
        Settings(
            student_model_url="https://student-model.example",
            student_model_topic_ids={},
            use_mock_student_model=False,
        )
    )

    with pytest.raises(JourneyVersionConflict) as conflict:
        asyncio.run(
            adapter.send_session_event(
                SessionOpenedEvent(
                    request_id="SESSION001:SESSION001:SESSION_OPENED",
                    event_type="SESSION_OPENED",
                    topic_id="T02",
                    student_id="ST001",
                    timestamp="2026-08-01T00:00:00Z",
                ),
                "token",
            )
        )
    assert "submit it once more" in str(conflict.value.detail)
    assert "journey_state" not in str(conflict.value.detail)
