import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.api import canvas as canvas_api
from app.adapters import provider, tutor_engine as tutor_engine_module
from app.adapters.student_model import StudentModelServiceAdapter
from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.adapters.vision_ocr import MockVisionOCRAdapter
from app.ai_engine.classifier import ClassificationRequest
from app.ai_engine.schemas import TutorResponse
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.models.work_artifact import (
    WorkArtifactPersistRequest,
    WorkArtifactPersistResponse,
)
from app.main import app
from app.models.adapters import (
    AdapterContext,
    AnnotationIntent,
    OCRTextRegion,
    RAGResult,
    StudentModelResult,
    TutorResult,
    TutorMistakeClassification,
    VisionOCRResult,
)
from app.models.canvas import CanvasSubmitRequest
from app.services import canvas_evidence, canvas_service, interaction_service, session_service
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


def _real_png_data_url() -> str:
    """A decodable PNG, for paths that actually render the page (PDF assembly).

    VALID_SNAPSHOT_DATA_URL only satisfies the base64 field validator; it is
    not real image bytes.
    """

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


@pytest.mark.parametrize(
    ("ocr_text", "mathml_operator"),
    [
        ("n-5", "−"),
        (r"n\times5", "×"),
        ("n+5", "＋"),
        ("n*5", "×"),
        ("n/5", "÷"),
        ("n=5", "＝"),
    ],
)
def test_mathml_confirmation_accepts_equivalent_operator_glyphs(
    ocr_text: str,
    mathml_operator: str,
) -> None:
    left, right = ocr_text[0], ocr_text[-1]
    ocr = VisionOCRResult(
        raw_ocr_text=ocr_text,
        detected_equation=ocr_text,
        detected_steps=[ocr_text],
        detected_regions=[
            OCRTextRegion(
                step_id="step-1",
                text=ocr_text,
                x=0.1,
                y=0.1,
                w=0.3,
                h=0.1,
                confidence=1.0,
            )
        ],
        final_answer=ocr_text,
        confidence=1.0,
        mathml_blocks=[
            f"<math><mi>{left}</mi><mo>{mathml_operator}</mo><mn>{right}</mn></math>"
        ],
        provider="mathpix",
    )

    confirmed = canvas_evidence._with_confirmed_mathml_regions(ocr)

    assert confirmed.detected_regions[0].mathml == ocr.mathml_blocks[0]


def test_mathml_confirmation_keeps_matching_regions_when_another_region_misses() -> None:
    ocr = VisionOCRResult(
        raw_ocr_text="n-5\nx+4",
        detected_equation="n-5\nx+4",
        detected_steps=["n-5", "x+4"],
        detected_regions=[
            OCRTextRegion(
                step_id="step-1",
                text="n-5",
                x=0.1,
                y=0.1,
                w=0.3,
                h=0.1,
                confidence=1.0,
            ),
            OCRTextRegion(
                step_id="step-2",
                text="x+4",
                x=0.1,
                y=0.3,
                w=0.3,
                h=0.1,
                confidence=1.0,
            ),
        ],
        final_answer="x+4",
        confidence=1.0,
        mathml_blocks=["<math><mi>n</mi><mo>−</mo><mn>5</mn></math>"],
        provider="mathpix",
    )

    confirmed = canvas_evidence._with_confirmed_mathml_regions(ocr)

    assert confirmed.detected_regions[0].mathml == ocr.mathml_blocks[0]
    assert confirmed.detected_regions[1].mathml is None


def _unified_voice_payload(
    session_id: str,
    student_id: str,
    turn_id: str,
    transcript: str,
) -> dict[str, object]:
    session = session_service._sessions[session_id]
    return {
        "session_id": session_id,
        "student_id": student_id,
        "interaction_type": "ANSWER_SUBMISSION",
        "input_source": "VOICE",
        "turn_id": turn_id,
        "voice_transcript": transcript,
        "transcript_confidence": 0.95,
        "transcript_final": True,
        "current_phase": session.current_phase,
        "concept_id": session.concept_id,
        "question_id": session.question_id,
        "hint_count": session.hint_count,
        "canvas_state": {
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "strokes": [
                {
                    "stroke_id": "stroke-1",
                    "tool": "pen",
                    "points": [{"x": 0.12, "y": 0.18}, {"x": 0.48, "y": 0.26}],
                    "width": 0.01,
                }
            ],
            "captured_at": "2026-08-10T10:00:00Z",
        },
    }


def _canvas_event(question_id: str | None, order_index: int) -> dict[str, object]:
    return {
        "order_index": order_index,
        "turn_id": "FRONTEND-LISTENING-TURN",
        "question_id": question_id,
        "actor": "STUDENT",
        "action_type": "WRITE",
        "content": "Student wrote a line.",
        "math_text": None,
        "target_object_id": "stroke-1",
        "bbox": {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1},
        "semantic_tag": None,
        "source_id": None,
        "active_state": "ACTIVE",
    }


async def _incorrect_ocr(
    adapter: MockVisionOCRAdapter,
    snapshot_data_url: str,
) -> VisionOCRResult:
    del adapter, snapshot_data_url
    return VisionOCRResult(
        raw_ocr_text="x = 4",
        detected_equation="x = 4",
        detected_steps=["x = 4"],
        final_answer="x = 4",
        confidence=0.95,
        provider="mock",
    )


async def _unexpected_ocr(
    adapter: MockVisionOCRAdapter,
    snapshot_data_url: str,
) -> VisionOCRResult:
    del adapter, snapshot_data_url
    raise AssertionError("rejected Canvas evidence reached OCR")


def test_canvas_semantic_text_normalizes_detected_relationships() -> None:
    ocr = VisionOCRResult(
        raw_ocr_text="",
        detected_equation="m + 7",
        detected_steps=[
            r"m \rightarrow change",
            r"7 \rightarrow fixed",
            "Operation → +",
        ],
        confidence=0.99,
    )

    assert canvas_service._semantic_canvas_text(ocr) == (
        "m  means  change\n7  means  fixed\nOperation  means  +"
    )


def test_canvas_endpoint_serializes_submissions_for_one_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_calls = 0
    maximum_active_calls = 0

    async def tracked_submit(
        request: CanvasSubmitRequest,
        access_token: str,
    ) -> None:
        nonlocal active_calls, maximum_active_calls
        del request, access_token
        active_calls += 1
        maximum_active_calls = max(maximum_active_calls, active_calls)
        await asyncio.sleep(0)
        active_calls -= 1
        return None

    monkeypatch.setattr(canvas_api, "submit_canvas", tracked_submit)
    request = CanvasSubmitRequest(
        session_id="SESSION001",
        student_id="ST001",
        snapshot_data_url=VALID_SNAPSHOT_DATA_URL,
        submission_role="STANDALONE_ATTEMPT",
    )

    async def submit_concurrently() -> None:
        await asyncio.gather(
            canvas_api.canvas_submit_endpoint(request, "token"),
            canvas_api.canvas_submit_endpoint(request, "token"),
        )

    asyncio.run(submit_concurrently())

    assert maximum_active_calls == 1


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
    assert body["submission_id"]
    assert body["status"] == "processed"
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
        "mathml": None,
    }
    assert body["ocr"]["final_answer"] == "x = 5"
    assert body["ocr"]["raw_ocr_text"] == "x + 4 = 9, x = 9 - 4, x = 5"
    assert body["ocr"]["confidence"] == 0.95
    assert body["ocr"]["needs_clarification"] is False
    assert body["ocr"]["provider"] == "mock"
    assert body["ocr"]["detected_shapes"] == []
    assert body["message"]
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


def test_canvas_submit_ocrs_each_page_in_order() -> None:
    session_id = _start_session("ST001")
    single_page_text = "x + 4 = 9, x = 9 - 4, x = 5"

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST001",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "additional_pages": [
                VALID_SNAPSHOT_DATA_URL,
                VALID_SNAPSHOT_DATA_URL,
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    # One attempt, one submission — not one per page.
    assert body["status"] == "processed"
    # Every page was recognised separately and combined in page order.
    assert body["ocr"]["raw_ocr_text"] == "\n".join([single_page_text] * 3)


def test_canvas_submit_without_additional_pages_is_unchanged() -> None:
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
    # Single-page submissions keep the unjoined single-page text.
    assert response.json()["ocr"]["raw_ocr_text"] == "x + 4 = 9, x = 9 - 4, x = 5"


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
            "turn_id": "TURN-ST013-CANVAS-1",
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
                "turn_id": f"TURN-{student_id}-CANVAS-1",
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
        expected_attempt = (
            "CORRECT_ATTEMPT"
            if phase == "PHASE_2_GUIDED_LEARNING"
            else "INCORRECT_ATTEMPT"
        )
        assert event_types[:3] == [
            "SESSION_OPENED",
            expected_initializer,
            expected_attempt,
        ]


def test_canvas_rejects_empty_question_response_without_erasing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", _incorrect_ocr)
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
    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", _incorrect_ocr)
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
                        "rescue_to_serve": {
                            "rescue_type": "TUTOR_SOLVED",
                            "micro_skill_id": "T02.M1",
                            "tutor_solved": {
                                "explanation": "Subtract 4 from both sides. The correct answer is x = 5.",
                                "final_answer": "x = 5",
                                "answer_steps": ["Subtract 4 from both sides."],
                            },
                        },
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
    assert response.json()["guided_rescue"]["rescue_type"] == "TUTOR_SOLVED"
    assert "correct answer is x = 5" in response.json()["tutor"]["tutor_message"]
    after = session_service._get_owned_session(session_id, "ST016")
    assert after.question_id == before.question_id
    assert after.current_question == before.current_question
    assert after.student_model_event is not None
    assert after.student_model_event.phase_payload is not None
    assert after.student_model_event.phase_payload.question_set is None
    assert after.active_student_model_question is not None
    assert after.active_student_model_question.question_id == before.question_id


def test_canvas_submit_sends_full_ocr_context_and_forwards_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts: list[AdapterContext] = []
    captured_events: list[StudentModelSessionEvent] = []
    captured_responses: list[StudentModelSessionEventResponse] = []
    classifier_requests: list[ClassificationRequest] = []
    original_evaluate = TutorEngineServiceAdapter.evaluate
    original_send = StudentModelServiceAdapter.send_session_event
    original_classify = tutor_engine_module.classify_student_response

    def capture_classification(request: ClassificationRequest) -> TutorResponse:
        classifier_requests.append(request)
        return original_classify(request)

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
    monkeypatch.setattr(
        tutor_engine_module,
        "classify_student_response",
        capture_classification,
    )
    session_id = _start_session("ST011")
    question_id = session_service._sessions[session_id].question_id

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST011",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "canvas_events": [_canvas_event(question_id, 0)],
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
    assert context.has_canvas_evidence is True
    assert [event.order_index for event in context.canvas_events] == [0]
    assert len(classifier_requests) == 1
    assert classifier_requests[0].canvas_events == context.canvas_events
    assert [event.event_type for event in captured_events] == [
        "SESSION_OPENED",
        "CORRECT_ATTEMPT",
        "INDEPENDENT_QUESTION_SET_REQUESTED",
    ]
    attempt_event = captured_events[1]
    assert isinstance(attempt_event, GuidedAttemptEvent)
    assert attempt_event.source_turn_id == context.source_turn_id
    assert attempt_event.request_id == (
        f"{session_id}:{context.source_turn_id}:CORRECT_ATTEMPT"
    )
    assert attempt_event.expected_journey_version > 0
    stored = client.get(f"/session/{session_id}", params={"student_id": "ST011"}).json()
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
    assert response.json()["status"] == "processed"
    stored_session = client.get(f"/session/{session_id}", params={"student_id": "ST013"}).json()
    assert stored_session["attempt_count"] == 0
    assert stored_session["per_question_history"] == []
    assert len(stored_session["canvas_submissions"]) == 1


def test_canvas_submit_stops_before_tutor_below_legacy_reliability_threshold(
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
            # The service setting is 0.75. This proves the legacy path also
            # applies Guided Learning's stricter 0.80 reliability threshold.
            confidence=0.78,
            needs_clarification=False,
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
    assert body["status"] == "CLARIFICATION_REQUIRED"
    assert body["message"] == "Please write out that step so I can check it."
    assert body["next_expected_input"] == "WRITE"
    assert body["canvas_draw"] == []
    assert body["localization_status"] == "uncertain"
    stored_session = client.get(f"/session/{session_id}", params={"student_id": "ST012"}).json()
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
    assert response.json()["message"]


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

    session_response = client.get(f"/session/{session_id}", params={"student_id": "ST002"})

    assert session_response.status_code == 200
    body = session_response.json()
    assert len(body["canvas_submissions"]) == 1
    submission_id = body["canvas_submissions"][0]["submission_id"]
    assert body["canvas_submissions"][0]["ocr"]["detected_equation"] == "x + 4 = 9"
    assert "detected_shapes" in body["canvas_submissions"][0]["ocr"]
    assert body["canvas_submissions"][0]["tutor"]["tutor_message"]
    assert "snapshot_data_url" not in session_response.text

    # History keeps only a lightweight reference; the image lives in the store.
    reference = body["canvas_submissions"][0]["snapshot_reference"]
    assert reference == f"canvas/{submission_id}.png"
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


def test_canvas_guided_validation_question_remains_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def send_validation_question(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        if event.event_type == "SESSION_OPENED":
            body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        else:
            assert event.event_type == "CORRECT_ATTEMPT"
            body = _event_response("CORRECT_ATTEMPT", event.request_id)
            source = _event_response("ORIENTATION_COMPLETED", event.request_id)
            source_payload = source["phase_payload"]
            assert isinstance(source_payload, dict)
            source_question_set = source_payload["question_set"]
            assert isinstance(source_question_set, dict)
            source_questions = source_question_set["questions"]
            assert isinstance(source_questions, list)
            validation_question = deepcopy(source_questions[0])
            assert isinstance(validation_question, dict)
            validation_question["question_id"] = "Q-T02-VAL-01"
            validation_question["question_usage_id"] = "QU-T02-VAL-01"
            student_view = validation_question["student_view"]
            assert isinstance(student_view, dict)
            student_view["question_text"] = "Validation: solve x + 2 = 7."
            journey = body["journey_state"]
            payload = body["phase_payload"]
            assert isinstance(journey, dict)
            assert isinstance(payload, dict)
            phase_state = journey["phase_2_guided_learning"]
            assert isinstance(phase_state, dict)
            phase_state.update(
                {
                    "completed_micro_skill_ids": [],
                    "remaining_micro_skill_ids": ["T02.M1"],
                    "current_question_id": "Q-T02-VAL-01",
                    "current_question_target_micro_skill_ids": ["T02.M1"],
                }
            )
            payload["question_set"] = {"questions": [validation_question]}
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "send_session_event",
        send_validation_question,
    )
    session_id = _start_session("ST039")
    before = session_service._sessions[session_id]
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST039",
            "turn_id": "TURN-ST039-CANVAS-1",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "canvas_events": [_canvas_event(before.question_id, 0)],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["current_phase"] == "GUIDED_PRACTICE"
    assert body["question_id"] == "Q-T02-VAL-01"
    assert body["current_question"] == "Validation: solve x + 2 = 7."
    assert "Validation: solve x + 2 = 7." in body["message"]
    assert "Validation: solve x + 2 = 7." in body["tutor"]["tutor_message"]
    stored = session_service._sessions[session_id]
    assert stored.canvas_state.snapshot_id is None
    assert stored.canvas_state.ocr_result is None
    assert before.question_id is not None
    assert stored.canvas_memory_by_question[before.question_id].updated_turn_id == (
        "TURN-ST039-CANVAS-1"
    )


def test_canvas_final_independent_attempt_is_recorded_before_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal_events: list[str] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        terminal_events.append(event.event_type)
        body = (
            _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
            if event.event_type == "SESSION_OPENED"
            else _session_opened_response("REVIEW")
        )
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    async def correct_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        student = StudentModelResult(
            mastery_status="MASTERED",
            continuity_status="on_track",
            recommended_entry_phase="REVIEW",
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

    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "send_session_event",
        send_session_event,
    )
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", correct_pipeline)
    session_id = _start_session("ST024")
    before = session_service._get_owned_session(session_id, "ST024")

    payload = {
        "session_id": session_id,
        "student_id": "ST024",
        "turn_id": "TURN-ST024-CANVAS-1",
        "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        "canvas_events": [_canvas_event(before.question_id, 0)],
    }
    response = client.post("/canvas/submit", json=payload)
    duplicate = client.post(
        "/canvas/submit",
        json={
            **payload,
            "canvas_events": [
                _canvas_event(before.question_id, 0),
                _canvas_event(before.question_id, 1),
            ],
        },
    )
    changed = client.post(
        "/canvas/submit",
        json={**payload, "snapshot_data_url": "data:image/png;base64,d29ybGQ="},
    )
    changed_strokes = client.post(
        "/canvas/submit",
        json={
            **payload,
            "strokes": [
                {
                    "stroke_id": "changed-stroke",
                    "tool": "pen",
                    "points": [{"x": 0.4, "y": 0.4}],
                    "width": 0.01,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "DUPLICATE_TURN"
    assert changed.status_code == 409
    assert changed_strokes.status_code == 409
    body = response.json()
    assert body["current_phase"] == "REVIEW"
    assert body["question_id"] is None
    assert body["current_question"] is None
    assert body["phase_changed"] is True

    stored = session_service._get_owned_session(session_id, "ST024")
    assert len(stored.canvas_submissions) == 1
    assert stored.canvas_state.snapshot_id is None
    assert stored.canvas_state.ocr_result is None
    assert list(stored.canvas_memory_by_question) == [before.question_id]
    assert stored.canvas_memory_by_question[before.question_id].updated_turn_id == (
        "TURN-ST024-CANVAS-1"
    )
    assert len(
        stored.canvas_memory_by_question[before.question_id].canvas_events
    ) == 1
    assert len(stored.per_question_history) == 1
    attempt = stored.per_question_history[0]
    assert attempt.question_id == before.question_id
    assert attempt.question_text == before.current_question
    assert attempt.phase == "INDEPENDENT_PRACTICE"
    assert attempt.evaluation == "CORRECT"
    assert attempt.input_source == "CANVAS"
    assert len(stored.canvas_submissions) == 1
    assert terminal_events.count("CORRECT_ATTEMPT") == 1


def _independent_practice_session(monkeypatch: pytest.MonkeyPatch) -> str:
    """Start a session sitting in Phase 3 with a correct-answer pipeline."""

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    async def correct_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        student = StudentModelResult(
            mastery_status="DEVELOPING",
            continuity_status="on_track",
            recommended_entry_phase="INDEPENDENT_PRACTICE",
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

    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "send_session_event",
        send_session_event,
    )
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", correct_pipeline)
    return _start_session("ST031")


def test_canvas_links_stored_work_artifact_to_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[WorkArtifactPersistRequest] = []

    async def persist_work_artifact(
        adapter: StudentModelServiceAdapter,
        request: WorkArtifactPersistRequest,
        access_token: str,
    ) -> WorkArtifactPersistResponse:
        del adapter, access_token
        persisted.append(request)
        return WorkArtifactPersistResponse(
            artifact_id="ART-P3-000124",
            pdf_url="https://blob.example/submission.pdf",
            page_count=request.page_count,
        )

    session_id = _independent_practice_session(monkeypatch)
    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "persist_work_artifact",
        persist_work_artifact,
    )

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST031",
            "turn_id": "TURN-ST031-CANVAS-1",
            "snapshot_data_url": _real_png_data_url(),
            "additional_pages": [_real_png_data_url()],
        },
    )

    assert response.status_code == 200, response.text
    stored = session_service._get_owned_session(session_id, "ST031")
    assert stored.per_question_history[-1].work_artifact_id == "ART-P3-000124"
    # One artifact per attempt, carrying both pages and their ordered OCR.
    assert len(persisted) == 1
    assert persisted[0].page_count == 2
    assert len(persisted[0].per_page_ocr_text) == 2
    assert persisted[0].combined_pdf_base64


def test_canvas_submission_survives_work_artifact_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_persist(
        adapter: StudentModelServiceAdapter,
        request: WorkArtifactPersistRequest,
        access_token: str,
    ) -> WorkArtifactPersistResponse:
        del adapter, request, access_token
        raise AdapterError("student_model", "storage unavailable")

    session_id = _independent_practice_session(monkeypatch)
    monkeypatch.setattr(
        StudentModelServiceAdapter,
        "persist_work_artifact",
        failing_persist,
    )

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST031",
            "turn_id": "TURN-ST031-CANVAS-2",
            "snapshot_data_url": _real_png_data_url(),
        },
    )

    # The student's turn is evaluated and routed as normal; only the Phase 4
    # replay of this attempt is lost.
    assert response.status_code == 200, response.text
    stored = session_service._get_owned_session(session_id, "ST031")
    assert stored.per_question_history[-1].work_artifact_id is None
    assert stored.per_question_history[-1].evaluation == "CORRECT"


def _incorrect_independent_tutor() -> TutorResult:
    return TutorResult(
        evaluation="INCORRECT",
        error_type="CONCEPTUAL_ERROR",
        intent="SUBMITTING_ANSWER",
        response_strategy="CORRECT_MISCONCEPTION",
        tutor_message="Diagnostic detail that must not be exposed.",
        tutor_message_voice="Diagnostic detail that must not be exposed.",
        voice_optimised=True,
        hint_level=0,
        answer_reveal_allowed=False,
        confidence=0.95,
        input_source="CANVAS",
        attempt_increment=1,
        recommended_conversation_action="WAIT_FOR_STUDENT",
        question_completed=True,
        answer_value_confirmed=False,
        reasoning_complete=True,
        selected_error_code="ERR-T02-SUBTRACTION-MISAPPLIED",
        independent_outcome="RESCUE_REQUIRED",
        independent_success=False,
        independent_attempt_terminal=True,
    )


def test_tc21_canvas_failure_requests_fresh_content_and_keeps_gap_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[StudentModelSessionEvent] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        events.append(event)
        body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
        body["request_id"] = event.request_id
        if event.event_type == "INCORRECT_ATTEMPT":
            body["phase_payload"] = None
            body["journey_state"]["phase_3_independent_practice"].update(
                {
                    "retry_required_micro_skill_ids": ["T02.M1"],
                    "used_question_ids": ["Q-T02-004"],
                    "current_question_id": None,
                }
            )
        if event.event_type == "FRESH_INDEPENDENT_QUESTION_REQUESTED":
            body["phase_payload"] = None
            body["routing"].update(
                {
                    "reason_code": "FRESH_CONTENT_UNAVAILABLE",
                    "reason": "No fresh content is available.",
                    "next_action": "WAIT_FOR_CONTENT",
                    "content_gap_detected": True,
                    "missing_micro_skill_ids": ["T02.M1"],
                }
            )
            body["status"].update(
                {
                    "status_code": "CONTENT_GAP",
                    "intervention_required": True,
                    "intervention_reason": "Missing content for T02.M1.",
                }
            )
        return StudentModelSessionEventResponse.model_validate(body)

    async def incorrect_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        return (
            RAGResult(documents=[], retrieval_confidence=0.0),
            StudentModelResult(
                mastery_status="DEVELOPING",
                continuity_status="on_track",
                recommended_entry_phase="INDEPENDENT_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=False,
            ),
            _incorrect_independent_tutor(),
        )

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", incorrect_pipeline)
    session_id = _start_session("ST025")
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST025",
            "turn_id": "TURN-TC21",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200, response.text
    assert [event.event_type for event in events[-2:]] == [
        "INCORRECT_ATTEMPT",
        "FRESH_INDEPENDENT_QUESTION_REQUESTED",
    ]
    fresh = events[-1]
    assert fresh.target_micro_skill_ids == ["T02.M1"]
    assert fresh.used_question_ids == ["Q-T02-004"]
    body = response.json()
    assert body["current_phase"] == "INDEPENDENT_PRACTICE"
    assert body["question_id"] is None
    assert body["message"] == "We'll review this one before a fresh independent check."
    assert body["tutor"] is None
    assert body["selected_error_code"] is None
    assert body["first_error_step"] is None
    assert body["phase3_review_evidence"] is None
    stored = session_service._sessions[session_id]
    assert stored.student_model_event is not None
    assert stored.student_model_event.status.status_code == "CONTENT_GAP"
    assert stored.student_model_event.routing.missing_micro_skill_ids == ["T02.M1"]


def test_tc20_failed_retry_uses_returned_prerequisites_and_retains_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[StudentModelSessionEvent] = []

    async def send_session_event(
        adapter: StudentModelServiceAdapter,
        event: StudentModelSessionEvent,
        access_token: str,
    ) -> StudentModelSessionEventResponse:
        del adapter, access_token
        events.append(event)
        if event.event_type == "SESSION_OPENED":
            body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
            body["journey_state"]["phase_3_independent_practice"]["retry_required_micro_skill_ids"] = ["T02.M1"]
        elif event.event_type == "INDEPENDENT_RETRY_COMPLETED":
            body = _session_opened_response("PHASE_3_INDEPENDENT_PRACTICE")
            body["phase_payload"] = None
            body["journey_state"]["recommended_entry_phase"] = "PHASE_2_GUIDED_LEARNING"
            body["journey_state"]["phase_3_independent_practice"].update(
                {"retry_required_micro_skill_ids": [], "unresolved_micro_skill_ids": ["T02.M1"]}
            )
            body["routing"].update(
                {
                    "reason_code": "FRESH_RETRY_FAILED",
                    "next_action": "CHECK_PREREQUISITES_AND_RETURN_TO_GUIDED",
                    "prerequisite_check_required": True,
                    "prerequisite_micro_skill_ids": ["T02.M2"],
                }
            )
        else:
            body = _session_opened_response("PHASE_2_GUIDED_LEARNING")
        body["request_id"] = event.request_id
        return StudentModelSessionEventResponse.model_validate(body)

    async def incorrect_pipeline(
        context: AdapterContext,
    ) -> tuple[RAGResult, StudentModelResult, TutorResult]:
        del context
        return (
            RAGResult(documents=[], retrieval_confidence=0.0),
            StudentModelResult(
                mastery_status="LEARNING_GAP",
                continuity_status="on_track",
                recommended_entry_phase="GUIDED_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=True,
            ),
            _incorrect_independent_tutor(),
        )

    monkeypatch.setattr(StudentModelServiceAdapter, "send_session_event", send_session_event)
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", incorrect_pipeline)
    session_id = _start_session("ST026")
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST026",
            "turn_id": "TURN-TC20",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
        },
    )

    assert response.status_code == 200, response.text
    assert [event.event_type for event in events[-2:]] == [
        "INDEPENDENT_RETRY_COMPLETED",
        "GUIDED_QUESTION_SET_REQUESTED",
    ]
    guided_request = events[-1]
    assert guided_request.target_micro_skill_ids == ["T02.M2"]
    body = response.json()
    assert body["prerequisite_repair"] == {
        "prerequisite_micro_skill_ids": ["T02.M2"],
        "reason_code": "FRESH_RETRY_FAILED",
    }
    stored = session_service._sessions[session_id]
    assert stored.prerequisite_repair_event is not None
    assert stored.prerequisite_repair_event.routing.prerequisite_micro_skill_ids == ["T02.M2"]


def test_unified_voice_canvas_validation_advances_for_complete_correct_work() -> None:
    session_id = _start_session("ST019")
    payload = _unified_voice_payload(
        session_id,
        "ST019",
        "TURN-UNIFIED-CORRECT",
        "Is this right?",
    )

    response = client.post("/interaction", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_canvas_solution_correct"] is True
    assert body["advance_to_next_question"] is True
    assert body["attempt_increment"] == 1
    assert body["feedback_type"] == "PRAISE"


def test_unified_voice_canvas_conflict_returns_clarification() -> None:
    session_id = _start_session("ST020")
    payload = _unified_voice_payload(
        session_id,
        "ST020",
        "TURN-UNIFIED-CONFLICT",
        "I got three.",
    )

    response = client.post("/interaction", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CLARIFICATION_REQUIRED"
    assert body["conversation_action"] == "REQUEST_CLARIFICATION"
    assert body["is_canvas_solution_correct"] is True
    assert body["attempt_increment"] == 0
    assert body["feedback_type"] == "CLARIFICATION"


def test_unified_voice_canvas_retries_require_identical_evidence() -> None:
    session_id = _start_session("ST021")
    payload = _unified_voice_payload(
        session_id,
        "ST021",
        "TURN-UNIFIED-RETRY",
        "Is this right?",
    )

    first = client.post("/interaction", json=payload)
    exact_retry = client.post("/interaction", json=payload)
    changed_payload = {**payload, "voice_transcript": "I got x equals four."}
    changed_retry = client.post("/interaction", json=changed_payload)

    assert first.status_code == 200, first.text
    assert exact_retry.status_code == 200, exact_retry.text
    assert exact_retry.json()["status"] == "DUPLICATE_TURN"
    assert changed_retry.status_code == 409


def test_unified_voice_canvas_confirms_a_correct_intermediate_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class IntermediateVision:
        async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
            del snapshot_data_url
            return VisionOCRResult(
                raw_ocr_text="x = 9 - 4",
                detected_equation="x + 4 = 9",
                detected_steps=["x = 9 - 4"],
                detected_regions=[
                    {
                        "text": "x = 9 - 4",
                        "x": 0.12,
                        "y": 0.18,
                        "w": 0.34,
                        "h": 0.08,
                        "confidence": 0.95,
                    }
                ],
                final_answer=None,
                confidence=0.95,
                provider="mock",
            )

    adapters = provider.get_adapters()
    monkeypatch.setattr(
        interaction_service,
        "get_adapters",
        lambda: replace(adapters, vision=IntermediateVision()),
    )
    session_id = _start_session("ST022")
    response = client.post(
        "/interaction",
        json=_unified_voice_payload(
            session_id,
            "ST022",
            "TURN-UNIFIED-INTERMEDIATE",
            "Is this right?",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_canvas_solution_correct"] is False
    assert body["advance_to_next_question"] is False
    assert body["conversation_action"] == "ACKNOWLEDGE_ANSWER"
    assert body["attempt_increment"] == 0
    assert body["feedback_type"] == "PRAISE"
    assert session_service._sessions[session_id].attempt_count == 0


def test_unified_voice_canvas_unclear_ocr_does_not_grade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnclearVision:
        async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
            del snapshot_data_url
            return VisionOCRResult(
                raw_ocr_text="x = ?",
                detected_equation="x + 4 = 9",
                final_answer="x = 5",
                confidence=0.4,
                needs_clarification=True,
                provider="mock",
            )

    adapters = provider.get_adapters()
    monkeypatch.setattr(
        interaction_service,
        "get_adapters",
        lambda: replace(adapters, vision=UnclearVision()),
    )
    session_id = _start_session("ST023")
    response = client.post(
        "/interaction",
        json=_unified_voice_payload(
            session_id,
            "ST023",
            "TURN-UNIFIED-UNCLEAR",
            "Is this right?",
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CLARIFICATION_REQUIRED"
    assert body["is_canvas_solution_correct"] is None
    assert body["advance_to_next_question"] is False
    assert body["attempt_increment"] == 0
    assert body["feedback_type"] == "CLARIFICATION"
    stored = session_service._sessions[session_id]
    assert stored.attempt_count == 0
    assert stored.question_id is not None
    memory = stored.canvas_memory_by_question[stored.question_id]
    assert memory.updated_turn_id == "TURN-UNIFIED-UNCLEAR"
    assert [stroke.stroke_id for stroke in memory.strokes] == ["stroke-1"]


def test_unified_voice_canvas_keeps_mathml_in_tutor_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mathml_blocks = [
        "<math><mi>x</mi><mo>+</mo><mn>4</mn><mo>=</mo><mn>9</mn></math>",
        "<math><mi>x</mi><mo>=</mo><mn>9</mn><mo>-</mo><mn>4</mn></math>",
        "<math><mi>x</mi><mo>=</mo><mn>5</mn></math>",
    ]
    captured_context: list[AdapterContext] = []

    class MathMLVision:
        async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
            del snapshot_data_url
            return VisionOCRResult(
                raw_ocr_text="x + 4 = 9\nx = 9 - 4\nx = 5",
                detected_equation="x + 4 = 9",
                detected_steps=["x + 4 = 9", "x = 9 - 4", "x = 5"],
                detected_regions=[
                    {"text": "x + 4 = 9", "x": 0.12, "y": 0.18, "w": 0.36, "h": 0.08, "confidence": 0.96},
                    {"text": "x = 9 - 4", "x": 0.12, "y": 0.30, "w": 0.34, "h": 0.08, "confidence": 0.95},
                    {"text": "x = 5", "x": 0.12, "y": 0.42, "w": 0.18, "h": 0.08, "confidence": 0.95},
                ],
                final_answer="x = 5",
                confidence=0.95,
                mathml_blocks=mathml_blocks,
                provider="mathpix",
            )

    async def capture_pipeline(context: AdapterContext):
        captured_context.append(context)
        return (
            RAGResult(documents=[], retrieval_confidence=0.0),
            StudentModelResult(
                mastery_status="DEVELOPING",
                continuity_status="on_track",
                recommended_entry_phase="GUIDED_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=False,
            ),
            TutorResult(
                evaluation="CORRECT",
                error_type="NONE",
                intent="ASKING_QUESTION",
                response_strategy="CONFIRM_CORRECT",
                tutor_message="Correct.",
                tutor_message_voice="Correct.",
                voice_optimised=True,
                hint_level=0,
                answer_reveal_allowed=False,
                confidence=0.95,
                input_source="VOICE",
                attempt_increment=1,
                recommended_conversation_action="ADVANCE_TO_NEXT_QUESTION",
                question_completed=True,
                answer_value_confirmed=True,
                reasoning_complete=True,
            ),
        )

    adapters = provider.get_adapters()
    monkeypatch.setattr(
        interaction_service,
        "get_adapters",
        lambda: replace(adapters, vision=MathMLVision()),
    )
    monkeypatch.setattr(interaction_service, "run_tutor_pipeline", capture_pipeline)
    session_id = _start_session("ST024")
    request = _unified_voice_payload(
        session_id,
        "ST024",
        "TURN-UNIFIED-MATHML",
        "Is this right?",
    )
    canvas_state = request["canvas_state"]
    assert isinstance(canvas_state, dict)
    canvas_state["canvas_events"] = [
        _canvas_event(session_service._sessions[session_id].question_id, 0)
    ]
    response = client.post(
        "/interaction",
        json=request,
    )

    assert response.status_code == 200, response.text
    assert captured_context[0].canvas_mathml_blocks == mathml_blocks
    assert [region.mathml for region in captured_context[0].canvas_regions] == mathml_blocks
    assert [event.order_index for event in captured_context[0].canvas_events] == [0]


def test_canvas_event_order_must_be_contiguous_from_zero() -> None:
    session_id = _start_session("ST030")
    question_id = session_service._sessions[session_id].question_id

    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST030",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "canvas_events": [_canvas_event(question_id, 1)],
        },
    )

    assert response.status_code == 422


def test_canvas_stale_question_is_rejected_before_ocr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", _unexpected_ocr)
    session_id = _start_session("ST031")
    before = session_service._sessions[session_id]
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST031",
            "turn_id": "TURN-ST031-CANVAS-1",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "canvas_events": [_canvas_event("STALE-QUESTION", 0)],
        },
    )

    assert response.status_code == 409
    assert response.json()["status"] == "STALE_TURN"
    after = session_service._sessions[session_id]
    assert after.attempt_count == before.attempt_count
    assert after.canvas_submissions == before.canvas_submissions
    assert after.canvas_memory_by_question == before.canvas_memory_by_question


@pytest.mark.parametrize("oversized_field", ["strokes", "canvas_events"])
def test_canvas_payload_caps_apply_before_ocr(
    monkeypatch: pytest.MonkeyPatch,
    oversized_field: str,
) -> None:
    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", _unexpected_ocr)
    student_id = "ST032" if oversized_field == "strokes" else "ST033"
    session_id = _start_session(student_id)
    question_id = session_service._sessions[session_id].question_id
    payload: dict[str, object] = {
        "session_id": session_id,
        "student_id": student_id,
        "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
    }
    if oversized_field == "strokes":
        payload["strokes"] = [
            {
                "stroke_id": "oversized",
                "tool": "pen",
                "points": [{"x": 0.1, "y": 0.1}] * 10_001,
                "width": 0.01,
            }
        ]
    else:
        payload["canvas_events"] = [
            _canvas_event(question_id, index) for index in range(501)
        ]

    response = client.post("/canvas/submit", json=payload)

    assert response.status_code == 413


@pytest.mark.parametrize(
    ("canvas_events", "expected_status"),
    [
        ([_canvas_event("STALE-QUESTION", 0)], 409),
        (
            [_canvas_event(None, index) for index in range(501)],
            413,
        ),
    ],
)
def test_interaction_rejects_stale_or_oversized_canvas_before_ocr(
    monkeypatch: pytest.MonkeyPatch,
    canvas_events: list[dict[str, object]],
    expected_status: int,
) -> None:
    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", _unexpected_ocr)
    student_id = "ST037" if expected_status == 409 else "ST038"
    session_id = _start_session(student_id)
    request = _unified_voice_payload(
        session_id,
        student_id,
        f"TURN-INTERACTION-REJECT-{expected_status}",
        "Please check this.",
    )
    canvas_state = request["canvas_state"]
    assert isinstance(canvas_state, dict)
    canvas_state["canvas_events"] = canvas_events

    response = client.post("/interaction", json=request)

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["status"] == "STALE_TURN"


def test_unclear_canvas_replaces_memory_for_the_same_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts: list[AdapterContext] = []
    original_evaluate = TutorEngineServiceAdapter.evaluate

    async def capture_evaluate(
        adapter: TutorEngineServiceAdapter,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        captured_contexts.append(context)
        return await original_evaluate(adapter, context, rag, student)

    async def unclear_ocr(
        adapter: MockVisionOCRAdapter,
        snapshot_data_url: str,
    ) -> VisionOCRResult:
        del adapter, snapshot_data_url
        return VisionOCRResult(
            raw_ocr_text="x = ?",
            detected_equation="x = ?",
            detected_steps=["x = ?"],
            confidence=0.4,
            needs_clarification=True,
            provider="mock",
        )

    monkeypatch.setattr(MockVisionOCRAdapter, "recognize", unclear_ocr)
    monkeypatch.setattr(TutorEngineServiceAdapter, "evaluate", capture_evaluate)
    session_id = _start_session("ST034")
    question_id = session_service._sessions[session_id].question_id
    assert question_id is not None
    base_payload: dict[str, object] = {
        "session_id": session_id,
        "student_id": "ST034",
        "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
    }
    first = client.post(
        "/canvas/submit",
        json={
            **base_payload,
            "turn_id": "TURN-ST034-CANVAS-1",
            "canvas_events": [_canvas_event(question_id, 0)],
        },
    )
    second = client.post(
        "/canvas/submit",
        json={
            **base_payload,
            "turn_id": "TURN-ST034-CANVAS-2",
            "strokes": [
                {
                    "stroke_id": "latest-stroke",
                    "tool": "pen",
                    "points": [{"x": 0.2, "y": 0.2}],
                    "width": 0.01,
                }
            ],
            "canvas_events": [
                _canvas_event(question_id, 0),
                _canvas_event(question_id, 1),
            ],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    stored = session_service._sessions[session_id]
    assert stored.attempt_count == 0
    assert len(stored.canvas_memory_by_question) == 1
    memory = stored.canvas_memory_by_question[question_id]
    assert memory.updated_turn_id == "TURN-ST034-CANVAS-2"
    assert [stroke.stroke_id for stroke in memory.strokes] == ["latest-stroke"]
    assert [event.order_index for event in memory.canvas_events] == [0, 1]
    assert stored.canvas_state.snapshot_id == "TURN-ST034-CANVAS-2"
    assert stored.canvas_state.ocr_result is not None
    retrieved = client.get(
        f"/session/{session_id}", params={"student_id": "ST034"}
    ).json()
    assert retrieved["canvas_memory_by_question"][question_id]["updated_turn_id"] == (
        "TURN-ST034-CANVAS-2"
    )
    follow_up = client.post(
        "/interaction",
        json={
            "session_id": session_id,
            "student_id": "ST034",
            "interaction_type": "ANSWER_SUBMISSION",
            "input_source": "TEXT",
            "turn_id": "TURN-ST034-TEXT-3",
            "text_input": "I am still working on it.",
            "current_phase": stored.current_phase,
            "concept_id": stored.concept_id,
            "question_id": question_id,
            "hint_count": stored.hint_count,
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    assert [event.order_index for event in captured_contexts[-1].canvas_events] == [
        0,
        1,
    ]


def test_interaction_duplicate_ignores_growing_canvas_events_after_advance() -> None:
    session_id = _start_session("ST035")
    question_id = session_service._sessions[session_id].question_id
    request = _unified_voice_payload(
        session_id,
        "ST035",
        "TURN-ST035-VOICE-1",
        "My answer is x equals five.",
    )
    canvas_state = request["canvas_state"]
    assert isinstance(canvas_state, dict)
    canvas_state["canvas_events"] = [_canvas_event(question_id, 0)]

    first = client.post("/interaction", json=request)
    retry_canvas_state = {
        **canvas_state,
        "canvas_events": [
            _canvas_event(question_id, 0),
            _canvas_event(question_id, 1),
        ],
    }
    duplicate = client.post(
        "/interaction",
        json={**request, "canvas_state": retry_canvas_state},
    )

    assert first.status_code == 200, first.text
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "DUPLICATE_TURN"
    assert duplicate.json()["attempt_increment"] == 0
    stored = session_service._sessions[session_id]
    assert question_id is not None
    assert stored.canvas_memory_by_question[question_id].updated_turn_id == (
        "TURN-ST035-VOICE-1"
    )


def test_canvas_submit_uses_shared_spatial_tokens_for_grounded_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_contexts: list[AdapterContext] = []

    class MathMLVision:
        async def recognize(self, snapshot_data_url: str) -> VisionOCRResult:
            del snapshot_data_url
            return VisionOCRResult(
                raw_ocr_text="4-y",
                detected_equation="4-y",
                detected_steps=["4-y"],
                detected_regions=[
                    OCRTextRegion(
                        text="4-y",
                        x=0.05,
                        y=0.05,
                        w=0.35,
                        h=0.15,
                        confidence=0.95,
                    )
                ],
                final_answer="x = 4",
                confidence=0.95,
                mathml_blocks=[
                    "<math><mrow><mn>4</mn><mo>-</mo><mi>y</mi></mrow></math>"
                ],
                provider="mathpix",
            )

    async def incorrect_evaluation(
        adapter: TutorEngineServiceAdapter,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        del adapter, rag, student
        captured_contexts.append(context)
        return TutorResult(
            evaluation="INCORRECT",
            error_type="OPPOSITE_OPERATION",
            intent="CANVAS_EVAL",
            response_strategy="CORRECT_MISTAKE",
            tutor_message="Check the sign.",
            tutor_message_voice="Check the sign.",
            voice_optimised=True,
            hint_level=1,
            answer_reveal_allowed=False,
            confidence=0.95,
            input_source="CANVAS",
            recommended_conversation_action="GIVE_HINT",
            question_completed=False,
            attempt_increment=1,
            mistake_classification=TutorMistakeClassification(
                status="mistake_found",
                mistake_step_id="step-1",
                target_token_ids=["step-1:token-2"],
                error_token="-",
                expected_token="+",
                confidence=0.95,
            ),
            annotation_intents=[
                AnnotationIntent(kind="circle_target", target_step_id="step-1")
            ],
        )

    adapters = provider.get_adapters()
    monkeypatch.setattr(
        canvas_service,
        "get_adapters",
        lambda: replace(adapters, vision=MathMLVision()),
    )
    monkeypatch.setattr(TutorEngineServiceAdapter, "evaluate", incorrect_evaluation)
    session_id = _start_session("ST036")
    question_id = session_service._sessions[session_id].question_id
    response = client.post(
        "/canvas/submit",
        json={
            "session_id": session_id,
            "student_id": "ST036",
            "turn_id": "TURN-ST036-CANVAS-1",
            "snapshot_data_url": VALID_SNAPSHOT_DATA_URL,
            "strokes": [
                {
                    "stroke_id": "s1",
                    "tool": "pen",
                    "points": [{"x": 0.1, "y": 0.1}, {"x": 0.12, "y": 0.12}],
                    "width": 0.01,
                },
                {
                    "stroke_id": "s2",
                    "tool": "pen",
                    "points": [{"x": 0.2, "y": 0.1}, {"x": 0.25, "y": 0.1}],
                    "width": 0.01,
                },
                {
                    "stroke_id": "s3",
                    "tool": "pen",
                    "points": [{"x": 0.3, "y": 0.1}, {"x": 0.32, "y": 0.15}],
                    "width": 0.01,
                },
            ],
            "canvas_events": [_canvas_event(question_id, 0)],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["localization_status"] == "grounded"
    assert len(captured_contexts) == 1
    context = captured_contexts[0]
    assert context.has_canvas_evidence is True
    assert context.canvas_mathml_blocks
    assert len(context.spatial_tokens) == 3
    assert context.canvas_events[0].question_id == question_id
    assert response.json()["canvas_draw"]
