from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.session import QuestionAttemptRecord
from app.services import session_service

client = TestClient(app)


def seed_graded_attempt(session_id: str) -> None:
    """/session/end refuses sessions with no graded attempts; seed one."""

    session = session_service._sessions[session_id]
    session_service._sessions[session_id] = session.model_copy(
        update={
            "per_question_history": [
                QuestionAttemptRecord(
                    question_id="ALG_EQ_GP_001",
                    question_text="Solve for x: x + 6 = 10",
                    phase="GUIDED_PRACTICE",
                    evaluation="CORRECT",
                    input_source="TEXT",
                    hint_level_used=0,
                    attempted_at=datetime.now(timezone.utc),
                )
            ]
        }
    )


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
    assert started["current_phase"] == "GUIDED_PRACTICE"
    assert started["current_question"] == "Solve for x: x + 6 = 10"
    assert started["question_id"] == "ALG_EQ_GP_001"
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
    assert started["ui_state"] == "GUIDED_PRACTICE"
    assert (
        started["message"]
        == "Let us start with a quick question to see where you are. Solve for x: x plus 6 equals 10."
    )
    assert started["show_canvas"] is True
    assert started["show_hint_button"] is True
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

    no_attempts = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST001"},
    )
    assert no_attempts.status_code == 409

    seed_graded_attempt(session_id)
    end_response = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST001"},
    )

    assert end_response.status_code == 200
    ended = end_response.json()
    assert ended["session_id"] == session_id
    assert ended["status"] == "ended"
    assert ended["message"] == "Session ended."
    review = ended["session_review"]
    assert review["student_facing_summary"]
    assert review["five_category_summary"]["category_1_strength"]
    assert review["guardrail_passed"] is True
    # Null categories are excluded from the spoken order.
    assert "category_2_first_error" not in review["voice_delivery_order"]
    assert "category_1_strength" in review["voice_delivery_order"]


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


def test_question_bank_fetch_maps_payload_and_excludes_served(monkeypatch) -> None:
    # fetch_question maps math_tutor_questions payloads to (text, answer, id)
    # and skips answer-less items and already-served ids.
    import asyncio

    from app.adapters import question_bank

    def _point(text, answer, question_id):
        point = type("P", (), {})()
        point.payload = {
            "question_text": text,
            "correct_answer": answer,
            "question_id": question_id,
        }
        return point

    class _FakeQdrant:
        async def scroll(self, collection_name, scroll_filter, limit, with_payload):
            assert collection_name == "math_tutor_questions"
            return (
                [
                    _point("Solve for x: x + 7 = 13", None, "ALG_1STEP_DIAG_F03"),
                    _point("Solve for x: x + 4 = 9", "x = 5", "ALG_1STEP_DIAG_F01"),
                    _point("Solve for x: x + 9 = 15", "x = 6", "ALG_1STEP_DIAG_F02"),
                ],
                None,
            )

    monkeypatch.setattr(question_bank, "_get_client", lambda: _FakeQdrant())
    result = asyncio.run(
        question_bank.fetch_question("ALG_LINEAR_ONE_STEP", "DIAGNOSTIC", ["ALG_1STEP_DIAG_F01"])
    )
    assert result == ("Solve for x: x + 9 = 15", "x = 6", "ALG_1STEP_DIAG_F02")


def test_session_start_stores_correct_answer_and_served_ids() -> None:
    from app.services import session_service

    response = client.post(
        "/session/start",
        json={
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200
    session = session_service._sessions[response.json()["session_id"]]
    assert session.correct_answer == "x = 4"
    assert session.served_question_ids == [session.question_id]
