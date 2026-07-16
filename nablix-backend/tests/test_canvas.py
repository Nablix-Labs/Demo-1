import pytest
from fastapi.testclient import TestClient

from app.adapters.student_model import StudentModelServiceAdapter
from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.core.config import get_settings
from app.main import app
from app.models.adapters import (
    AdapterContext,
    RAGResult,
    StudentModelEvent,
    StudentModelResult,
    TutorResult,
    VisionOCRResult,
)
from app.services import canvas_service, session_service
from app.services.snapshot_store import get_snapshot

client = TestClient(app, headers={"Authorization": "Bearer test-token"})

VALID_SNAPSHOT_DATA_URL = "data:image/png;base64,aGVsbG8="


def _start_session(student_id: str) -> str:
    response = client.post(
        "/session/start",
        json={
            "student_id": student_id,
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "interaction_mode": "TEXT",
            "initial_phase": "GUIDED_PRACTICE",
        },
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    # The mock OCR fixture shows work for the diagnostic question; pin the
    # session to it since guided sessions now start on the GP question.
    session = session_service._sessions[session_id]
    session_service._sessions[session_id] = session.model_copy(
        update={
            "current_question": "Solve for x: x + 4 = 9",
            "question_id": "ALG_EQ_DIAG_001",
            "correct_answer": "x = 5",
        }
    )
    return session_id


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
    assert body["tutor"]["canvas_feedback"]["has_feedback"] is True
    assert [
        step["evaluation"] for step in body["tutor"]["canvas_feedback"]["step_feedback"]
    ] == ["CORRECT", "CORRECT", "CORRECT"]
    assert body["canvas_draw"] == []
    assert body["latency"]["total_latency_ms"] >= 0
    assert {"ocr_latency_ms", "tutor_latency_ms"} <= body["latency"].keys()

    end = client.post(
        "/session/end",
        json={"session_id": session_id, "student_id": "ST001"},
    )
    summary = end.json()["session_summary"]
    assert summary["session_performance"]["total_attempts"] == 1
    assert summary["session_performance"]["canvas_submissions"] == 1
    assert len(summary["canvas_feedback_history"]) == 1


def test_canvas_submit_sends_full_ocr_context_and_forwards_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts: list[AdapterContext] = []
    captured_events: list[StudentModelEvent] = []
    original_evaluate = TutorEngineServiceAdapter.evaluate

    async def capture_evaluate(
        adapter: TutorEngineServiceAdapter,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        captured_contexts.append(context)
        return await original_evaluate(adapter, context, rag, student)

    async def capture_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelEvent,
        context: AdapterContext,
        access_token: str,
    ) -> StudentModelResult:
        captured_events.append(event)
        return StudentModelResult(
            mastery_status="DEVELOPING",
            continuity_status="on_track",
            recommended_entry_phase=context.current_phase or "GUIDED_PRACTICE",
            hint_dependency_score=0.0,
            intervention_required=False,
        )

    monkeypatch.setattr(TutorEngineServiceAdapter, "evaluate", capture_evaluate)
    monkeypatch.setattr(StudentModelServiceAdapter, "update_from_event", capture_event)
    session_id = _start_session("ST011")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST011",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    assert len(captured_contexts) == 1
    context = captured_contexts[0]
    assert context.question == "Solve for x: x + 4 = 9"
    assert context.correct_answer == "x = 5"
    assert context.current_phase == "GUIDED_PRACTICE"
    assert context.attempt_count == 1
    assert context.detected_equation == "x + 4 = 9"
    assert context.detected_steps == ["x + 4 = 9", "x = 9 - 4", "x = 5"]
    assert context.ocr_confidence == 0.95
    assert [region.step_id for region in context.canvas_regions] == [
        "step-1",
        "step-2",
        "step-3",
    ]
    assert len(captured_events) == 1
    assert client.get(f"/session/{session_id}").json()["attempt_count"] == 1


def test_voice_canvas_attachment_does_not_record_a_second_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelEvent,
        context: AdapterContext,
        access_token: str,
    ) -> StudentModelResult:
        raise AssertionError(f"Voice attachment forwarded duplicate event: {event}")

    monkeypatch.setattr(StudentModelServiceAdapter, "update_from_event", unexpected_event)
    session_id = _start_session("ST013")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST013",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "submission_role": "VOICE_ATTACHMENT",
        },
    )

    assert response.status_code == 200
    stored_session = client.get(f"/session/{session_id}").json()
    assert stored_session["attempt_count"] == 0
    assert stored_session["per_question_history"] == []
    assert len(stored_session["canvas_submissions"]) == 1


def test_canvas_submit_stops_before_tutor_when_ocr_needs_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def low_confidence_ocr(
        adapter: MockVisionOCRAdapter,
        snapshot_data_url: str,
    ) -> VisionOCRResult:
        return VisionOCRResult(
            raw_ocr_text="x + ? = 9",
            detected_equation="x + ? = 9",
            detected_steps=["x + ? = 9"],
            confidence=0.5,
            needs_clarification=True,
        )

    async def unexpected_tutor_call(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        raise AssertionError(f"Tutor Engine received low-confidence OCR: {context}")

    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", low_confidence_ocr)
    monkeypatch.setattr(canvas_service, "run_tutor_pipeline", unexpected_tutor_call)
    session_id = _start_session("ST012")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST012",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tutor"]["evaluation"] == "UNCLEAR"
    assert body["tutor"]["response_strategy"] == "CLARIFY"
    assert body["canvas_draw"] == []
    stored_session = client.get(f"/session/{session_id}").json()
    assert stored_session["attempt_count"] == 0
    assert stored_session["canvas_submissions"][0]["tutor"]["evaluation"] == "UNCLEAR"


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
    from tests.test_session import seed_graded_attempt

    session_id = _start_session("ST007")
    seed_graded_attempt(session_id)
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
