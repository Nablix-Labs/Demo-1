import asyncio

from app.services.voice.streaming import streaming_server
from app.services.voice.streaming.streaming_server import _canvas_draw_from


def test_voice_canvas_attaches_before_canonical_voice_interaction(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class FakeWebSocket:
        async def send_json(self, payload: dict[str, object]) -> None:
            calls.append(("send", payload))

    class FakeTTS:
        async def generate_speech_stream(self, **kwargs):
            del kwargs
            if False:
                yield b""

    async def fake_submit(*args: object) -> dict[str, object]:
        calls.append(("canvas", args))
        return {"submission_id": "canvas-1", "canvas_draw": []}

    async def fake_evaluate(*args: object) -> dict[str, object]:
        calls.append(("voice", args))
        return {
            "message": "Keep going.",
            "message_voice": "Keep going.",
            "accepted_turn_id": "TURN-BROWSER-1",
            "tutor_turn_id": "TURN-TUTOR-1",
            "visual_cue": {
                "show": True,
                "cue_type": "VC-1",
                "description": "Look here.",
                "actions": [
                    {
                        "action": "HIGHLIGHT_TOKEN",
                        "target": "x",
                        "style": "VARIABLE",
                    }
                ],
            },
        }

    monkeypatch.setattr(streaming_server, "submit_canvas_work", fake_submit)
    monkeypatch.setattr(streaming_server, "evaluate_voice_transcript", fake_evaluate)
    monkeypatch.setattr(streaming_server, "get_tts_adapter", lambda provider: FakeTTS())

    asyncio.run(
        streaming_server.process_and_respond(
            FakeWebSocket(),
            "SESSION001",
            "ST001",
            "x equals five",
            0.9,
            1.0,
            "test-token",
            "data:image/png;base64,YQ==",
            None,
            None,
            "TURN-BROWSER-1",
            "TURN-TUTOR-0",
            True,
        )
    )

    assert [kind for kind, _ in calls[:2]] == ["canvas", "voice"]
    voice_args = calls[1][1]
    assert isinstance(voice_args, tuple)
    assert voice_args[-1] == "canvas-1"
    tutor_response = next(
        payload
        for kind, payload in calls
        if kind == "send" and isinstance(payload, dict) and payload.get("type") == "tutor_response"
    )
    assert tutor_response["accepted_turn_id"] == "TURN-BROWSER-1"
    assert tutor_response["tutor_turn_id"] == "TURN-TUTOR-1"
    assert tutor_response["visual_cue"]["actions"][0]["target"] == "x"


def test_canvas_draw_is_forwarded() -> None:
    assert _canvas_draw_from({"canvas_draw": [{"elements": []}]}) == [
        {"elements": []}
    ]
