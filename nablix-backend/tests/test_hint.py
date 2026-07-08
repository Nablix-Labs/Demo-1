from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _start_guided_session(student_id: str) -> str:
    start_response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert start_response.status_code == 200
    session_id: str = start_response.json()["session_id"]

    interaction_response = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": student_id,
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "text_input": "Is 7 + 5 = 13?",
            "current_phase": "GUIDED_PRACTICE",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "question_id": "ALG_EQ_DIAG_001",
            "hint_count": 0,
        },
    )
    assert interaction_response.status_code == 200
    return session_id


def _hint_body(session_id: str, student_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "session_id": session_id,
        "student_id": student_id,
        "current_phase": "GUIDED_PRACTICE",
        "current_hint_count": 0,
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": "ALG_EQ_DIAG_001",
    }
    body.update(overrides)
    return body


def test_hint_request_returns_tutor_hint() -> None:
    session_id = _start_guided_session("ST101")

    response = client.post("/hint/request", json=_hint_body(session_id, "ST101"))

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["student_id"] == "ST101"
    assert body["hint_level"] == 1
    assert body["hint"] == "Here is a hint: think about the operation being used on x."
    assert body["response_strategy"] == "GUIDED_HINT"
    assert body["answer_reveal_allowed"] is False


def test_hint_level_uses_stored_count_plus_one() -> None:
    session_id = _start_guided_session("ST102")

    first_response = client.post("/hint/request", json=_hint_body(session_id, "ST102"))
    second_response = client.post(
        "/hint/request",
        json=_hint_body(session_id, "ST102", current_hint_count=1),
    )

    assert first_response.status_code == 200
    assert first_response.json()["hint_level"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["hint_level"] == 2


def test_hint_request_rejects_stale_hint_count() -> None:
    session_id = _start_guided_session("ST103")
    first_response = client.post("/hint/request", json=_hint_body(session_id, "ST103"))

    stale_response = client.post("/hint/request", json=_hint_body(session_id, "ST103"))

    assert first_response.status_code == 200
    assert stale_response.status_code == 409


def test_hint_request_rejects_unavailable_phase() -> None:
    start_response = client.post(
        "/session/start",
        json={
            "student_id": "ST104",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert start_response.status_code == 200
    session_id: str = start_response.json()["session_id"]

    response = client.post(
        "/hint/request",
        json=_hint_body(session_id, "ST104", current_phase="DIAGNOSTIC"),
    )

    assert response.status_code == 409


def test_hint_request_rejects_malformed_session_id() -> None:
    response = client.post("/hint/request", json=_hint_body("bad", "ST001"))

    assert response.status_code == 422
    assert response.json()["field"] == "session_id"
