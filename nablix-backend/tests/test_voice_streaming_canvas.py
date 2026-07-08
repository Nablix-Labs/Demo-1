from app.services.voice.streaming.streaming_server import (
    _canvas_draw_from,
    _tutor_response_from_canvas,
)


def test_canvas_result_maps_to_streaming_tutor_response() -> None:
    result: dict[str, object] = {
        "tutor": {
            "tutor_message": "Circle the mistake.",
            "tutor_message_voice": "I circled the mistake.",
        },
        "canvas_draw": [{"elements": []}],
    }

    assert _tutor_response_from_canvas(result) == {
        "message": "Circle the mistake.",
        "message_voice": "I circled the mistake.",
    }
    assert _canvas_draw_from(result) == [{"elements": []}]
