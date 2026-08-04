import pytest
from fastapi.testclient import TestClient

from app.adapters import provider
from app.adapters.student_model import StudentModelServiceAdapter
from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.core.config import Settings, get_settings
from app.main import app
from app.models.adapters import (
    AdapterContext,
    RAGResult,
    StudentModelResult,
    TutorResult,
    VisionOCRResult,
)
from app.services import canvas_service, interaction_service, session_service
from app.services.snapshot_store import get_snapshot
from app.models.student_model_session import (
    GuidedAttemptEvent,
    StudentModelSessionEvent,
    StudentModelSessionEventResponse,
)
from tests.test_session_events import (
    _event_response,
    _recommended_not_started_response,
    _session_opened_response,
)

client = TestClient(app, headers={"Authorization": "Bearer test-token"})

VALID_SNAPSHOT_DATA_URL = "data:image/png;base64,aGVsbG8="


@pytest.fixture(autouse=True)
def schema_student_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        student_model_url="https://student-model.test",
        student_model_topic_codes={"ALG_LINEAR_ONE_STEP": "ALG-ORI-02"},
        use_mock_student_model=False,
        use_mock_voice=True,
        use_mock_vision=True,
        use_openai_ai_engine=False,
        qdrant_url="https://qdrant.test",
        qdrant_api_key="test-key",
    )

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = (
            _session_opened_response("PHASE_2_GUIDED_LEARNING")
            if event.event_type == "SESSION_OPENED"
            else _event_response(event.event_type, event.request_id)
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(provider, "get_settings", lambda: settings)
    monkeypatch.setattr(session_service, "get_settings", lambda: settings)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)


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
    session_id = response.json()["session_id"]
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


def test_canvas_initializes_recommended_phase_before_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_types: list[str] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        event_types.append(event.event_type)
        body = (
            _recommended_not_started_response("PHASE_3_INDEPENDENT_PRACTICE")
            if event.event_type == "SESSION_OPENED"
            else _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    session_id = _start_session("ST013")

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST013",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200
    assert event_types[:2] == [
        "SESSION_OPENED",
        "INDEPENDENT_QUESTION_SET_REQUESTED",
    ]


@pytest.mark.parametrize(
    (
        "phase",
        "expected_initializer",
        "student_id",
        "remaining_skills",
        "expected_status",
    ),
    [
        (
            "PHASE_2_GUIDED_LEARNING",
            "GUIDED_QUESTION_SET_REQUESTED",
            "ST014",
            None,
            200,
        ),
        (
            "PHASE_3_INDEPENDENT_PRACTICE",
            "INDEPENDENT_QUESTION_SET_REQUESTED",
            "ST017",
            None,
            200,
        ),
        (
            "PHASE_3_INDEPENDENT_PRACTICE",
            None,
            "ST018",
            [],
            503,
        ),
    ],
)
def test_canvas_repairs_in_progress_question_before_building_answer_context(
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    expected_initializer: str | None,
    student_id: str,
    remaining_skills: list[str] | None,
    expected_status: int,
) -> None:
    event_types: list[str] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        event_types.append(event.event_type)
        body = (
            _recommended_not_started_response(phase)
            if event.event_type == "SESSION_OPENED"
            else _session_opened_response(phase)
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    session_id = _start_session(student_id)
    stored = session_service._get_owned_session(session_id, student_id)
    assert stored.student_model_event is not None
    stale_event = stored.student_model_event
    phase_state = (
        stale_event.journey_state.phase_2_guided_learning
        if phase == "PHASE_2_GUIDED_LEARNING"
        else stale_event.journey_state.phase_3_independent_practice
    )
    phase_updates: dict[str, object] = {
        "status": "IN_PROGRESS",
        "current_question_id": None,
    }
    if remaining_skills is not None:
        phase_updates["remaining_micro_skill_ids"] = remaining_skills
    stale_phase = phase_state.model_copy(update=phase_updates)
    phase_field = (
        "phase_2_guided_learning"
        if phase == "PHASE_2_GUIDED_LEARNING"
        else "phase_3_independent_practice"
    )
    stale_journey = stale_event.journey_state.model_copy(
        update={phase_field: stale_phase}
    )
    assert stale_event.phase_payload is not None
    assert stale_event.phase_payload.question_set is not None
    empty_question_set = stale_event.phase_payload.question_set.model_copy(
        update={"questions": []}
    )
    stale_payload = stale_event.phase_payload.model_copy(
        update={"question_set": empty_question_set}
    )
    session_service._sessions[session_id] = stored.model_copy(
        update={
            "current_question": None,
            "question_id": None,
            "student_model_event": stale_event.model_copy(
                update={"journey_state": stale_journey, "phase_payload": stale_payload}
            ),
        }
    )

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": student_id,
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == expected_status, response.text
    if expected_initializer is None:
        assert event_types == ["SESSION_OPENED"]
        assert response.json()["message"] == (
            "Student Model returned an active Independent Practice journey "
            "without a question or remaining target skills."
        )
    else:
        assert event_types[:3] == [
            "SESSION_OPENED",
            expected_initializer,
            "INCORRECT_ATTEMPT",
        ]


def test_canvas_rejects_empty_question_response_without_erasing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _start_session("ST015")
    before = session_service._get_owned_session(session_id, "ST015")

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        response = StudentModelSessionEventResponse.model_validate(
            _event_response(event.event_type, event.request_id)
        )
        assert response.phase_payload is not None
        assert response.phase_payload.question_set is not None
        empty_question_set = response.phase_payload.question_set.model_copy(
            update={"questions": []}
        )
        return response.model_copy(
            update={
                "phase_payload": response.phase_payload.model_copy(
                    update={"question_set": empty_question_set}
                )
            }
        )

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST015",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 503
    assert response.json()["message"] == (
        "Student Model returned no active question for PHASE_2_GUIDED_LEARNING."
    )
    after = session_service._get_owned_session(session_id, "ST015")
    assert after.question_id == before.question_id
    assert after.current_question == before.current_question
    assert after.student_model_event == before.student_model_event


def test_canvas_preserves_question_metadata_for_guided_rescue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _start_session("ST016")
    before = session_service._get_owned_session(session_id, "ST016")

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        response = StudentModelSessionEventResponse.model_validate(
            _event_response(event.event_type, event.request_id)
        )
        assert response.phase_payload is not None
        return response.model_copy(
            update={
                "phase_payload": response.phase_payload.model_copy(
                    update={
                        "payload_type": "RESCUE",
                        "question_set": None,
                        "rescue_to_serve": {"tutor_solved": {"steps": []}},
                    }
                )
            }
        )

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST016",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200, response.text
    after = session_service._get_owned_session(session_id, "ST016")
    assert after.question_id == before.question_id
    assert after.current_question == before.current_question
    assert after.student_model_event is not None
    assert after.student_model_event.phase_payload is not None
    assert after.student_model_event.phase_payload.question_set is not None


def test_canvas_submit_sends_full_ocr_context_and_forwards_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts: list[AdapterContext] = []
    captured_events: list[StudentModelSessionEvent] = []
    captured_responses: list[StudentModelSessionEventResponse] = []
    original_evaluate = TutorEngineServiceAdapter.evaluate
    original_send = StudentModelServiceAdapter.send_session_event

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
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        captured_events.append(event)
        result = await original_send(adapter, event, access_token)
        captured_responses.append(result)
        return result

    monkeypatch.setattr(TutorEngineServiceAdapter, "evaluate", capture_evaluate)
    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", capture_event)
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
    assert [event.event_type for event in captured_events] == [
        "SESSION_OPENED",
        "INCORRECT_ATTEMPT",
    ]
    attempt_event = captured_events[1]
    assert isinstance(attempt_event, GuidedAttemptEvent)
    assert attempt_event.source_turn_id == context.source_turn_id
    assert attempt_event.request_id == (
        f"{session_id}:{context.source_turn_id}:INCORRECT_ATTEMPT"
    )
    assert attempt_event.expected_journey_version > 0
    stored = client.get(f"/session/{session_id}").json()
    assert stored["attempt_count"] == 0
    assert len(stored["per_question_history"]) == 1
    persisted_session = session_service._get_owned_session(session_id, "ST011")
    assert persisted_session.student_model_event is not None
    assert persisted_session.student_model_event.journey_state.version == (
        captured_responses[-1].journey_state.version
    )


def test_voice_canvas_attachment_does_not_record_a_second_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = _start_session("ST013")
    original_send = StudentModelServiceAdapter.send_session_event

    async def unexpected_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        raise AssertionError(f"Voice attachment forwarded duplicate event: {event}")

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", unexpected_event)

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

    async def unexpected_tutor_call(*args: object) -> object:
        raise AssertionError(f"Tutor Engine received low-confidence OCR: {args}")

    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", low_confidence_ocr)
    monkeypatch.setattr(
        canvas_service,
        "process_answer_with_session_event",
        unexpected_tutor_call,
    )
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


def test_canvas_submit_rejects_missing_session_after_memory_loss() -> None:
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

    assert response.status_code == 404


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


def test_canvas_correct_same_phase_routes_next_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A correct standalone canvas answer with no phase change advances to the
    # next unseen question, exactly like the /interaction path.
    async def fake_pipeline(context: AdapterContext):
        student = StudentModelResult(
            mastery_status="DEVELOPING",
            continuity_status="on_track",
            recommended_entry_phase="GUIDED_PRACTICE",
            hint_dependency_score=0.0,
            intervention_required=False,
        )
        tutor = TutorResult(
            evaluation="CORRECT",
            error_type="NONE",
            intent="SUBMITTING_ANSWER",
            response_strategy="CONFIRM_CORRECT",
            tutor_message="Correct.",
            tutor_message_voice="Correct.",
            voice_optimised=True,
            hint_level=0,
            answer_reveal_allowed=False,
            confidence=0.95,
            input_source="CANVAS",
            attempt_increment=1,
            recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION",
            question_completed=True,
            answer_value_confirmed=True,
            reasoning_complete=True,
        )
        return RAGResult(documents=[], retrieval_confidence=0.0), student, tutor

    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", fake_pipeline)
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
    assert body["phase_changed"] is True
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["question_id"] == "Q-T02-004"

    stored = session_service._sessions[session_id]
    assert stored.question_id == "Q-T02-004"
    assert stored.attempt_count == 0
    assert stored.question_completed is False
    assert stored.question_number == 1
