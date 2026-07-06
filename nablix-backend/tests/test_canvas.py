from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import session_service
from app.services.snapshot_store import get_snapshot

client = TestClient(app)

VALID_SNAPSHOT_DATA_URL = "data:image/png;base64,aGVsbG8="


def _start_session(student_id: str) -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
        },
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_canvas_submit_returns_mock_ocr_result() -> None:
    session_id = _start_session("ST001")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["student_id"] == "ST001"
    assert body["status"] == "processed"
    assert body["submission_id"]
    assert body["snapshot_reference"] == f"canvas/{body['submission_id']}.png"
    assert body["ocr"]["detected_equation"] == "x + 4 = 9"
    assert body["ocr"]["detected_steps"] == ["x + 4 = 9", "x = 9 - 4", "x = 5"]
    assert body["ocr"]["detected_regions"][0] == {
        "step_id": "step-1",
        "text": "x + 4 = 9",
        "x": 0.12,
        "y": 0.18,
        "w": 0.36,
        "h": 0.08,
        "confidence": 0.96,
    }
    assert body["ocr"]["final_answer"] == "x = 5"
    assert body["ocr"]["raw_ocr_text"] == "x + 4 = 9, x = 9 - 4, x = 5"
    assert body["ocr"]["confidence"] == 0.95
    assert body["ocr"]["needs_clarification"] is False
    assert body["ocr"]["provider"] == "mock"
    assert body["ocr"]["detected_shapes"] == []
    assert body["tutor"]["tutor_message"]
    assert body["canvas_draw"] == []
    assert body["latency"]["total_latency_ms"] >= 0
    assert {"ocr_latency_ms", "tutor_latency_ms"} <= body["latency"].keys()


def test_canvas_submit_accepts_optional_transcript() -> None:
    session_id = _start_session("ST010")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST010",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "transcript": "x equals five",
            "transcript_confidence": 0.9,
        },
    )

    assert response.status_code == 200
    assert response.json()["tutor"]["tutor_message"]


def test_canvas_submit_stores_ocr_without_serializing_snapshot() -> None:
    session_id = _start_session("ST002")

    submit_response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST002",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )
    assert submit_response.status_code == 200

    session_response = client.get(f"/session/{session_id}")

    assert session_response.status_code == 200
    body = session_response.json()
    assert len(body["canvas_submissions"]) == 1
    assert body["canvas_submissions"][0]["submission_id"] == submit_response.json()["submission_id"]
    assert body["canvas_submissions"][0]["ocr"]["detected_equation"] == "x + 4 = 9"
    assert "detected_shapes" in body["canvas_submissions"][0]["ocr"]
    assert body["canvas_submissions"][0]["tutor"]["tutor_message"]
    assert "snapshot_data_url" not in session_response.text

    # History keeps only a lightweight reference; the image lives in the store.
    reference = body["canvas_submissions"][0]["snapshot_reference"]
    assert reference == f"canvas/{submit_response.json()['submission_id']}.png"
    assert get_snapshot(reference) == VALID_SNAPSHOT_DATA_URL


def test_canvas_submit_recovers_demo_session_after_memory_loss() -> None:
    session_id = _start_session("ST001")
    session_service._sessions.clear()

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_canvas_submit_rejects_malformed_snapshot() -> None:
    response = client.post(
        "/canvas/submit",
        json={"session_id": "SESSION001", "student_id": "ST001", "snapshot_data_url": "aGVsbG8="},
    )

    assert response.status_code == 422
    assert response.json()["field"] == "snapshot_data_url"


def test_canvas_submit_rejects_oversize_snapshot() -> None:
    session_id = _start_session("ST003")
    settings = get_settings()
    oversized_snapshot = "data:image/png;base64," + ("A" * (settings.max_snapshot_bytes + 4))

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST003",
            "snapshot_data_url": oversized_snapshot,
        },
    )

    assert response.status_code == 413


def test_canvas_submit_returns_404_for_unknown_session() -> None:
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": "SESSION777",
            "student_id": "ST004",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 404


def test_canvas_submit_returns_404_for_student_mismatch() -> None:
    session_id = _start_session("ST005")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST006",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 404


def test_canvas_submit_returns_409_for_ended_session() -> None:
    session_id = _start_session("ST007")
    end_response = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST007"},
    )
    assert end_response.status_code == 200

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST007",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 409
