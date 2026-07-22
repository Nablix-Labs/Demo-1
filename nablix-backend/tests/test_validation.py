from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app, headers={"Authorization": "Bearer test-token"})


def _valid_interaction_body(session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "student_id": "ST101",
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "TEXT",
        "text_input": "I think x equals 5",
        "current_phase": "GUIDED_PRACTICE",
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": "ALG_EQ_DIAG_001",
        "hint_count": 0,
    }


def _start_session() -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": "ST101",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_validation_returns_missing_field_code() -> None:
    response = client.post(
        "/session/start",
        json={"concept_id": "ALG_LINEAR_ONE_STEP", "interaction_mode": "TEXT"},
        headers={"x-request-id": "REQ001"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "MISSING_FIELD"
    assert body["message"] == "student_id is required."
    assert body["field"] == "student_id"
    assert body["request_id"] == "REQ001"


def test_validation_returns_invalid_format_code() -> None:
    response = client.get("/session/bad", headers={"x-request-id": "REQ002"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_FORMAT"
    assert body["message"] == "session_id must follow the format SESSION followed by three digits."
    assert body["field"] == "session_id"
    assert body["request_id"] == "REQ002"


def test_validation_returns_input_too_long_code() -> None:
    session_id = _start_session()
    body = _valid_interaction_body(session_id)
    body["text_input"] = "x" * 501

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INPUT_TOO_LONG"
    assert body["message"] == "text_input must be 500 characters or fewer."
    assert body["field"] == "text_input"


def test_validation_returns_invalid_value_for_interaction_type() -> None:
    session_id = _start_session()
    body = _valid_interaction_body(session_id)
    body["interaction_type"] = "WRONG"

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_VALUE"
    assert body["field"] == "interaction_type"


def test_validation_returns_invalid_value_for_current_phase() -> None:
    session_id = _start_session()
    body = _valid_interaction_body(session_id)
    body["current_phase"] = "WRONG"

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_VALUE"
    assert body["field"] == "current_phase"


def test_validation_returns_invalid_json_code() -> None:
    response = client.post(
        "/session/start",
        content='{"student_id": "ST101"',
        headers={"content-type": "application/json", "x-request-id": "REQ006"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_JSON"
    assert body["message"] == "Request body must be valid JSON."
    assert body["field"] is None
    assert body["request_id"] == "REQ006"
