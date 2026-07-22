import asyncio

from fastapi.testclient import TestClient

from app.main import app
from app.services.voice.streaming import streaming_server

client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def test_streaming_tutor_call_forwards_bearer_token(monkeypatch) -> None:
    captured_headers: dict[str, str] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"message": "ok"}

    class FakeClient:
        async def post(
            self,
            path: str,
            *,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> FakeResponse:
            assert path == "/voice/transcript"
            captured_headers.update(headers)
            return FakeResponse()

    monkeypatch.setattr(streaming_server, "get_backend_http_client", FakeClient)

    asyncio.run(
        streaming_server.evaluate_voice_transcript(
            "SESSION001",
            "ST001",
            "x equals five",
            0.94,
            1.0,
            "test-token",
        )
    )

    assert captured_headers == {"Authorization": "Bearer test-token"}


def _start_session(student_id: str) -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "VOICE",
            "initial_phase": "DIAGNOSTIC",
        },
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_voice_returns_mock_transcript() -> None:
    response = client.post(
        "/voice",
        json={"session_id": "SESSION001", "student_id": "ST001", "audio_reference": "audio/clip-1.wav"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"].startswith("I got twelve")
    assert body["confidence"] == 0.94
    assert body["language"] == "en"


def test_voice_rejects_empty_audio_reference() -> None:
    response = client.post(
        "/voice",
        json={"session_id": "SESSION001", "student_id": "ST001", "audio_reference": "   "},
    )

    assert response.status_code == 422
    assert response.json()["field"] == "audio_reference"


def test_voice_rejects_malformed_student_id() -> None:
    response = client.post(
        "/voice",
        json={"session_id": "SESSION001", "student_id": "X1", "audio_reference": "audio/clip-1.wav"},
    )

    assert response.status_code == 422
    assert response.json()["field"] == "student_id"


def test_voice_session_start_sets_stream_active_state() -> None:
    session_id = _start_session("ST010")

    response = client.post(
        "/voice/session/start",
        json={"session_id": session_id, "student_id": "ST010"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["student_id"] == "ST010"
    assert body["stream_active"] is True
    assert body["current_turn"] == "STUDENT"
    assert body["voice_session_token"] == f"mock_voice_token_{session_id}"
    assert body["fallback_active"] is False

    session_response = client.get(f"/session/{session_id}")
    assert session_response.status_code == 200
    assert session_response.json()["voice_state"]["stream_active"] is True


def test_voice_transcript_routes_through_interaction_flow() -> None:
    session_id = _start_session("ST011")
    start_response = client.post(
        "/voice/session/start",
        json={"session_id": session_id, "student_id": "ST011"},
    )
    assert start_response.status_code == 200

    response = client.post(
        "/voice/transcript",
        json={
            "session_id": session_id,
            "student_id": "ST011",
            "transcript": "I think x equals four",
            "confidence": 0.94,
            "audio_duration_seconds": 3.2,
            "turn": "STUDENT",
            "timestamp": "2026-06-10T10:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["student_id"] == "ST011"
    assert body["message"] == "Let us review the equation and try the next step carefully."
    assert body["message_voice"] == "Let us review the equation and try the next step carefully."
    assert body["voice_state"]["stream_active"] is True
    assert body["voice_state"]["current_turn"] == "STUDENT"
    assert body["voice_state"]["last_transcript_confidence"] == 0.94
    assert body["interaction_mode"] == "VOICE"


def test_voice_transcript_normalizes_spoken_correct_answer() -> None:
    session_id = _start_session("ST013")

    response = client.post(
        "/voice/transcript",
        json={
            "session_id": session_id,
            "student_id": "ST013",
            "transcript": "x equals five",
            "confidence": 0.94,
            "audio_duration_seconds": 3.2,
            "turn": "STUDENT",
            "timestamp": "2026-06-10T10:00:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Correct. Nice work explaining your answer."
    assert body["message_voice"] == "Correct. Nice work explaining your answer."


def test_voice_transcript_rejects_invalid_confidence() -> None:
    session_id = _start_session("ST012")

    response = client.post(
        "/voice/transcript",
        json={
            "session_id": session_id,
            "student_id": "ST012",
            "transcript": "I think x equals four",
            "confidence": 1.4,
            "audio_duration_seconds": 3.2,
            "turn": "STUDENT",
            "timestamp": "2026-06-10T10:00:00Z",
        },
    )

    assert response.status_code == 422
    assert response.json()["field"] == "confidence"


def test_voice_stream_websocket_accepts_connection() -> None:
    with client.websocket_connect(
        "/voice/stream?session=SESSION001&student_id=ST001"
    ) as websocket:
        websocket.close()


def test_voice_stream_forwards_session_query_param(monkeypatch) -> None:
    """Frontends have sent both ?session= and ?session_id=; both must reach voice_stream."""
    captured: dict[str, str] = {}

    async def fake_voice_stream(ws, session="default", student_id="ST001"):
        captured["session"] = session
        captured["student_id"] = student_id
        await ws.accept()
        await ws.close()

    monkeypatch.setattr("app.api.voice.voice_stream", fake_voice_stream)

    for query in ("session=SESSION001", "session_id=SESSION001"):
        captured.clear()
        with client.websocket_connect(f"/voice/stream?{query}&student_id=ST042"):
            pass
        assert captured == {"session": "SESSION001", "student_id": "ST042"}, query
