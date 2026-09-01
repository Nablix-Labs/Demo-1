import logging

import pytest
from fastapi.testclient import TestClient

from app.core.logger import logger as app_logger
from app.main import app


client = TestClient(app, headers={"Authorization": "Bearer test-token"})
SESSION_ID = "SESSION101"


def _valid_interaction_body(session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "student_id": "ST101",
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "TEXT",
        "turn_id": "TURN-VALIDATION-1",
        "text_input": "I think x equals 5",
        "current_phase": "GUIDED_PRACTICE",
        "concept_id": "ALG_LINEAR_ONE_STEP",
        "question_id": "ALG_EQ_DIAG_001",
        "hint_count": 0,
    }


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
    assert body["message"] == (
        "session_id must follow the format SESSION followed by three digits "
        "or a UUID hex string."
    )
    assert body["field"] == "session_id"
    assert body["request_id"] == "REQ002"


def test_validation_returns_input_too_long_code() -> None:
    body = _valid_interaction_body(SESSION_ID)
    body["text_input"] = "x" * 501

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INPUT_TOO_LONG"
    assert body["message"] == "text_input must be 500 characters or fewer."
    assert body["field"] == "text_input"


def test_validation_returns_invalid_value_for_interaction_type() -> None:
    body = _valid_interaction_body(SESSION_ID)
    body["interaction_type"] = "WRONG"

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_VALUE"
    assert body["field"] == "interaction_type"


def test_validation_returns_invalid_value_for_current_phase() -> None:
    body = _valid_interaction_body(SESSION_ID)
    body["current_phase"] = "WRONG"

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "INVALID_VALUE"
    assert body["field"] == "current_phase"


def test_validation_requires_stable_turn_id() -> None:
    body = _valid_interaction_body(SESSION_ID)
    del body["turn_id"]

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    assert response.json()["field"] == "turn_id"


def test_interaction_requires_canvas_state_for_rest_voice_turn() -> None:
    body = _valid_interaction_body(SESSION_ID)
    body.update(
        {
            "input_source": "VOICE",
            "text_input": None,
            "voice_transcript": "Is this right?",
            "transcript_confidence": 0.95,
            "transcript_final": True,
        }
    )

    response = client.post("/interaction", json=body)

    assert response.status_code == 422
    assert response.json()["message"] == "canvas_state is required for REST VOICE answer submissions."


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


def test_a_422_names_every_rejected_field_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A frontend field mismatch showed up in the VM journal as a bare 422: the
    response names only the first bad field, and it goes to the browser, not the
    journal. Field paths and safe IDs only -- never the student's answer."""

    app_logger.addHandler(caplog.handler)
    body = _valid_interaction_body(SESSION_ID)
    body["interaction_type"] = "NOT_A_REAL_TYPE"
    body["hint_count"] = "not a number"
    try:
        with caplog.at_level(logging.WARNING):
            assert client.post("/interaction", json=body).status_code == 422
    finally:
        app_logger.removeHandler(caplog.handler)

    record = next(
        r for r in caplog.records if r.getMessage() == "request_validation_rejected"
    )
    assert record.route == "/interaction"
    assert "body.interaction_type" in record.rejected_field_paths
    assert "body.hint_count" in record.rejected_field_paths
    assert record.session_id == SESSION_ID
    assert record.turn_id == "TURN-VALIDATION-1"
    assert not any("I think x equals 5" in str(v) for v in vars(record).values())
