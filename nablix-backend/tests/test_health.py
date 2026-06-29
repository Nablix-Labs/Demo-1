from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_typed_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["app"] == "Nablix AI Math Tutor API"
    assert body["version"] == "1.0.0"
    assert body["mode"] == "mock"
    assert body["timestamp"].endswith("+00:00")


def test_cors_allows_local_frontend_preflight() -> None:
    response = client.options(
        "/session/start",
        headers={
            "origin": "http://127.0.0.1:3000",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
