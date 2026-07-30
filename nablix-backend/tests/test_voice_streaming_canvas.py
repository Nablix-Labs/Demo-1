from app.services.voice.streaming.streaming_server import (
    _canvas_draw_from,
    _support_fields_from,
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


def test_streaming_forwards_only_authorised_support_fields() -> None:
    result: dict[str, object] = {
        "show_visual_cue": True,
        "visual_cue": {
            "show": True,
            "cue_type": "VC-T02-COEFFICIENT-COUNT",
            "description": "Count the repeated equal terms.",
        },
        "show_scaffold_panel": True,
        "scaffold_id": "SCF-T02-WRITE-COMPACT",
        "current_scaffold_step_id": "SCF-T02-WR-S1",
        "scaffold_step_number": 1,
        "scaffold_step_text": "Which term or factor is repeated?",
        "scaffold_step_voice": "Which term or factor is repeated?",
        "total_scaffold_steps": 4,
        "canonical_answer": "4y",
        "scaffold_expected_response": "y",
    }

    forwarded = _support_fields_from(result)

    assert forwarded["show_visual_cue"] is True
    assert forwarded["current_scaffold_step_id"] == "SCF-T02-WR-S1"
    assert forwarded["scaffold_step_text"] == "Which term or factor is repeated?"
    assert "canonical_answer" not in forwarded
    assert "scaffold_expected_response" not in forwarded
