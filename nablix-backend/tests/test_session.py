from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_session_start_get_and_end_flow() -> None:
    start_response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "VOICE",
        },
    )

    assert start_response.status_code == 200
    started = start_response.json()
    session_id = started["session_id"]
    assert session_id.startswith("SESSION")
    assert started["status"] == "started"
    assert started["student_id"] == "ST001"
    assert started["concept_id"] == "ALG_LINEAR_ONE_STEP"
    assert started["interaction_mode"] == "VOICE"
    assert started["current_phase"] == "DIAGNOSTIC"
    assert started["current_question"] == "Solve for x: x + 4 = 9"
    assert started["question_id"] == "ALG_EQ_DIAG_001"
    assert started["question_number"] == 1
    assert started["voice_state"] == {
        "stream_active": False,
        "current_turn": "STUDENT",
        "last_transcript_confidence": None,
        "fallback_active": False,
    }
    assert started["canvas_state"] == {
        "canvas_active": True,
        "snapshot_id": None,
        "ocr_result": None,
    }
    assert started["ui_state"] == "DIAGNOSTIC"
    assert (
        started["message"]
        == "Let us start with a quick question to see where you are. Solve for x: x plus 4 equals 9."
    )
    assert started["show_canvas"] is True
    assert started["show_hint_button"] is False
    assert started["show_visual_cue"] is False
    assert started["show_scaffold_panel"] is False
    assert started["scaffold_steps"] == []
    assert started["allow_text_input"] is True
    assert started["allow_voice_input"] is True
    assert started["hint_count"] == 0
    assert started["canvas_submissions"] == []

    get_response = client.get(f"/session/{session_id}")

    assert get_response.status_code == 200
    assert get_response.json() == started

    end_response = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST001"},
    )

    assert end_response.status_code == 200
    ended = end_response.json()
    assert ended["session_id"] == session_id
    assert ended["status"] == "ended"
    assert ended["message"] == "Session ended."


def test_session_start_rejects_invalid_interaction_mode() -> None:
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TELEPATHY",
        },
    )

    assert response.status_code == 422
    assert response.json()["field"] == "interaction_mode"


def test_session_start_accepts_initial_phase_for_app_deep_links() -> None:
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
            "initial_phase": "GUIDED_PRACTICE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["ui_state"] == "GUIDED_PRACTICE"
    assert body["show_hint_button"] is True


def test_get_session_rejects_malformed_session_id() -> None:
    response = client.get("/session/bad")

    assert response.status_code == 422
    assert response.json()["field"] == "session_id"


def test_get_session_returns_404_for_unknown_valid_session_id() -> None:
    response = client.get("/session/SESSION777")

    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "HTTP_ERROR"
    assert body["message"] == "Session with ID SESSION777 was not found."
