import asyncio

import httpx
import pytest

from app.adapters import http_utils
from app.core.exceptions import AdapterRequestRejected


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
