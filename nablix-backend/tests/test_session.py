from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.models.session import QuestionAttemptRecord, SessionEndRequest
from app.services import session_service

client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def test_generated_session_ids_are_unique_and_valid() -> None:
    session_ids = [session_service._build_session_id() for _ in range(1001)]

    assert len(set(session_ids)) == 1001
    assert all(session_id.startswith("SESSION") for session_id in session_ids)
    for session_id in session_ids:
        SessionEndRequest(session_id=session_id, student_id="ST001")


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
