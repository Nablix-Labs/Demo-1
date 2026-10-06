"""Real loopback HTTP checks for the pending Student Model profile contract.

Proves Demo-1 forwarding and validation, not deployed database persistence.
"""

import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.core.config import Settings
from app.main import app


def profile(student_id: str) -> dict[str, object]:
    return {
        "student_id": student_id, "student_code": f"ST{student_id}",
        "display_name": "Original name", "email": "student@example.test",
        "tier": "tier_3", "account_status": "active",
        "age_band": "11–14 (KS3)", "grade_band": "Year 9", "preferred_mode": "balanced",
        "preferences": {"input_mode": "text", "panel_side": "left"},
        "guardians": [], "consents": None, "avatar_url": None,
    }


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, str, dict[str, object]]]]:
    records: dict[str, dict[str, object]] = {"student-one": profile("1"), "student-two": profile("2")}
    seen: list[tuple[str, str, dict[str, object]]] = []
    retry_calls = 0

    class ProfileServer(BaseHTTPRequestHandler):
        def reply(self, status: int, body: dict[str, object]) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self) -> None:
            nonlocal retry_calls
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            seen.append((self.command, token, {}))
            if self.path != "/students/me/profile":
                self.reply(404, {"message": "Wrong path"})
            elif token == "expired":
                self.reply(401, {"message": "Internal identity detail"})
            elif token == "other-role":
                self.reply(403, {"message": "Forbidden role"})
            elif token == "malformed":
                self.reply(200, {"student_id": "1"})
            elif token == "unavailable":
                self.reply(503, {"message": "service unavailable"})
            elif token == "retry":
                retry_calls += 1
                if retry_calls < 3:
                    self.reply(503, {"message": "temporarily unavailable"})
                else:
                    self.reply(200, records["student-one"])
            elif token in records:
                self.reply(200, records[token])
            else:
                self.reply(401, {"message": "Unknown token"})

        def do_PATCH(self) -> None:
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            body: dict[str, object] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.command, token, body))
            if token not in records:
                self.reply(401, {"message": "Unknown token"})
                return
            previous = records[token]
            preference_changes = body.get("preferences", {})
            assert isinstance(preference_changes, dict)
            previous_preferences = previous["preferences"]
            assert isinstance(previous_preferences, dict)
            records[token] = previous | body | {"preferences": previous_preferences | preference_changes}
            self.reply(200, records[token])

    server = ThreadingHTTPServer(("127.0.0.1", 0), ProfileServer)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = Settings(student_model_url=f"http://127.0.0.1:{server.server_port}", adapter_request_retry_count=2)
    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    try:
        yield seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_get_patch_get_preserves_omissions_and_uses_only_the_callers_token(upstream: list[tuple[str, str, dict[str, object]]]) -> None:
    client = TestClient(app)
    headers = {"Authorization": "Bearer student-one"}
    assert client.get("/students/me/profile", headers=headers).json()["display_name"] == "Original name"
    assert client.get("/students/me/profile?student_id=2", headers=headers).json()["student_id"] == "1"
    changed = client.patch("/students/me/profile", headers=headers, json={"display_name": "  Chiru  ", "preferences": {"panel_side": "right"}})
    assert changed.status_code == 200
    assert changed.json()["display_name"] == "Chiru"
    assert changed.json()["preferences"] == {"input_mode": "text", "panel_side": "right"}
    assert changed.json()["grade_band"] == "Year 9"
    assert upstream[-1] == ("PATCH", "student-one", {"display_name": "Chiru", "preferences": {"panel_side": "right"}})
    assert TestClient(app).get("/students/me/profile", headers=headers).json() == changed.json()
    other = client.get("/students/me/profile", headers={"Authorization": "Bearer student-two"})
    assert other.json()["display_name"] == "Original name"
    assert other.json()["student_id"] == "2"
    cleared = client.patch("/students/me/profile", headers=headers, json={"grade_band": None})
    assert cleared.status_code == 200
    assert cleared.json()["grade_band"] is None


@pytest.mark.parametrize("changes", [
    {}, {"student_id": "2"}, {"email": "other@example.test"}, {"tier": "admin"},
    {"account_status": "active"}, {"guardians": []}, {"avatar_url": "https://example.test/photo"},
    {"consents": []}, {"display_name": "   "}, {"age_band": "unknown"},
    {"grade_band": "Year 12"}, {"preferred_mode": None},
    {"preferences": {}}, {"preferences": {"input_mode": "video"}},
    {"preferences": {"panel_side": None}}, {"preferences": {"verified": True}},
])
def test_invalid_and_protected_fields_never_reach_student_model(upstream: list[tuple[str, str, dict[str, object]]], changes: dict[str, object]) -> None:
    response = TestClient(app).patch("/students/me/profile", headers={"Authorization": "Bearer student-one"}, json=changes)
    assert response.status_code == 422
    assert upstream == []


def test_missing_auth_never_reaches_student_model(upstream: list[tuple[str, str, dict[str, object]]]) -> None:
    client = TestClient(app)
    assert client.get("/students/me/profile").status_code == 401
    assert client.patch("/students/me/profile", json={"display_name": "Chiru"}).status_code == 401
    assert upstream == []


@pytest.mark.parametrize("token,status", [("expired", 401), ("other-role", 403), ("malformed", 503)])
def test_upstream_rejection_or_invalid_profile_is_explicit(upstream: list[tuple[str, str, dict[str, object]]], token: str, status: int) -> None:
    response = TestClient(app).get("/students/me/profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status
    assert "Internal identity detail" not in response.text
    assert "127.0.0.1" not in response.text
    assert len(upstream) == 1


def test_transient_errors_retry_the_same_authenticated_request(upstream: list[tuple[str, str, dict[str, object]]]) -> None:
    response = TestClient(app).get("/students/me/profile", headers={"Authorization": "Bearer retry"})
    assert response.status_code == 200
    assert upstream == [("GET", "retry", {})] * 3


def test_exhausted_retries_raise_an_explicit_service_error(upstream: list[tuple[str, str, dict[str, object]]]) -> None:
    response = TestClient(app).get("/students/me/profile", headers={"Authorization": "Bearer unavailable"})
    assert response.status_code == 503
    assert response.json()["error_code"] == "ADAPTER_UNAVAILABLE"
    assert upstream == [("GET", "unavailable", {})] * 3
