from fastapi.testclient import TestClient

from app.adapters import provider, student_model
from app.adapters.http_utils import JsonObject
from app.core.config import Settings
from app.main import app


client = TestClient(app, headers={"Authorization": "Bearer frontend-token"})


def _student_model_response(request_id: str, phase: str) -> JsonObject:
    return {
        "schema_version": "3.0",
        "request_id": request_id,
        "processed_at": "2026-07-28T08:00:00Z",
        "journey_state": {
            "student_id": "ST001",
            "topic_id": "ALG-ORI-02",
            "mastery_status": "NEW_LEARNER",
            "continuity_status": "ON_TRACK",
            "current_phase": phase,
            "recommended_entry_phase": phase,
        },
        "phase_payload": {
            "phase": phase,
            "payload_type": "QUESTION_SET",
            "question_set": {"questions": []},
        },
        "event_result": None,
        "routing": {
            "reason_code": "DIAGNOSTIC_STARTED",
            "reason": "Diagnostic question set delivered.",
            "next_action": "WAIT_FOR_STUDENT_RESPONSE",
        },
        "status": {
            "success": True,
            "status_code": "OK",
            "intervention_required": False,
            "warnings": [],
            "operational_errors": [],
        },
    }


def test_learning_event_forwards_saravanan_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = Settings(
        student_model_base_url="https://student-model.example",
        student_model_token="service-token",
    )

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: JsonObject,
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> JsonObject:
        captured.update(
            adapter_name=adapter_name,
            url=url,
            payload=payload,
            headers=headers,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
        )
        return _student_model_response(
            str(payload["request_id"]),
            "PHASE_0_DIAGNOSTIC",
        )

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    request_body = {
        "request_id": "REQ-DEMO3-TC01",
        "event_type": "DIAGNOSTIC_QUESTION_SET_REQUESTED",
        "topic_id": "ALG-ORI-02",
        "student_id": "ST001",
        "timestamp": "2026-07-28T08:00:00Z",
    }
    response = client.post("/learning-events", json=request_body)

    assert response.status_code == 200
    assert response.json()["request_id"] == request_body["request_id"]
    assert response.json()["schema_version"] == "3.0"
    assert captured["url"] == "https://student-model.example/session/event"
    assert captured["headers"] == {"Authorization": "Bearer service-token"}
    assert captured["payload"] == request_body


def test_learning_event_keeps_phase_specific_fields(monkeypatch) -> None:
    captured: dict[str, object] = {}
    settings = Settings(
        student_model_base_url="https://student-model.example",
        student_model_token="service-token",
    )

    async def fake_post_json(
        adapter_name: str,
        url: str,
        payload: JsonObject,
        headers: dict[str, str],
        timeout_seconds: int,
        retry_count: int,
    ) -> JsonObject:
        del adapter_name, url, headers, timeout_seconds, retry_count
        captured["payload"] = payload
        return _student_model_response(
            str(payload["request_id"]),
            "PHASE_1_ORIENTATION",
        )

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(student_model, "post_json", fake_post_json)

    request_body = {
        "request_id": "REQ-DEMO3-TC04",
        "event_type": "WORKED_EXAMPLE_REQUESTED",
        "topic_id": "ALG-ORI-02",
        "student_id": "ST001",
        "target_micro_skill_ids": ["T02.M8"],
    }
    response = client.post("/learning-events", json=request_body)

    assert response.status_code == 200
    assert captured["payload"] == request_body


def test_learning_event_requires_student_model_configuration(monkeypatch) -> None:
    monkeypatch.setattr(provider, "get_settings", lambda: Settings())

    response = client.post(
        "/learning-events",
        json={
            "request_id": "REQ-DEMO3-MISSING-CONFIG",
            "event_type": "DIAGNOSTIC_QUESTION_SET_REQUESTED",
            "topic_id": "ALG-ORI-02",
            "student_id": "ST001",
        },
    )

    assert response.status_code == 503
    assert "NABLIX_STUDENT_MODEL_BASE_URL" in response.json()["message"]
