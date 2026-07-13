import json
import logging

from fastapi.testclient import TestClient
import pytest

from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.ai_engine import openai_client
from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.ai_engine.prompt_registry import (
    build_openai_tutor_messages,
    build_openai_tutor_prompt_metadata,
    load_prompt_registry,
    serialize_session_context,
)
from app.ai_engine.schemas import CanvasTextRegion
from app.core.config import Settings, get_settings
from app.core.logger import StructuredJsonFormatter
from app.main import app, prompt_registry as startup_prompt_registry
from app.models.adapters import AdapterContext, OCRTextRegion, RAGResult, StudentModelResult, TutorEngineRequest


client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_openai_ai_engine_by_default(monkeypatch):
    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "false")
    monkeypatch.delenv("NABLIX_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ai_engine_classify_returns_valid_tutor_response() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 3 = 7",
            "expected_answer": "x = 4",
            "student_input": "x = 5",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "SUBMITTING_ANSWER"
    assert body["evaluation"] == "INCORRECT"
    assert body["response_strategy"] == "GUIDED_HINT"
    assert body["answer_reveal_allowed"] is False
    assert body["safety_check"]["passed"] is True
    assert body["guardrail_check"]["passed"] is True


def test_startup_uses_validated_cached_prompt_registry() -> None:
    assert startup_prompt_registry is load_prompt_registry()


class _FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.status_code = 200
        self.text = content
        self._content = content

    def json(self) -> dict[str, str]:
        return {"output_text": self._content}


def test_ai_engine_can_use_openai_when_feature_flag_is_enabled(monkeypatch) -> None:
    request_bodies = []
    responses = [
        _FakeOpenAIResponse('{"evaluation": "PARTIALLY_CORRECT", "confidence": 0.88}'),
        _FakeOpenAIResponse(
            '{"error_type": "ARITHMETIC_ERROR", "error_description": "Arithmetic mismatch.", "confidence": 0.9}'
        ),
        _FakeOpenAIResponse(
            '{"tutor_message": "Check the inverse operation first.", '
            '"tutor_message_voice_optimised": "Check the inverse operation first.", "confidence": 0.86}'
        ),
    ]

    class _FakeOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_FakeOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return responses.pop(0)

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NABLIX_OPENAI_AI_ENGINE_MODEL", "gpt-test")
    monkeypatch.setenv("NABLIX_OPENAI_PROMPT_CACHE_KEY_ENABLED", "false")
    monkeypatch.setattr(openai_client.httpx, "Client", _FakeOpenAIClient)
    get_settings.cache_clear()

    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 3 = 7",
            "expected_answer": "x = 4",
            "student_input": "x = 5",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
        },
    )

    get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == "PARTIALLY_CORRECT"
    assert body["error_type"] == "ARITHMETIC_ERROR"
    assert body["tutor_message"] == "Check the inverse operation first."
    assert body["answer_reveal_allowed"] is False
    assert body["guardrail_check"]["passed"] is True
    assert len(request_bodies) == 3

    registry = load_prompt_registry()
    for request_body in request_bodies:
        messages = request_body["input"]
        assert messages[0] == {"role": "system", "content": registry.layer_1_core}
        assert messages[1]["role"] == "system"
        assert "PHASE 2" in messages[1]["content"]
        assert messages[2]["role"] == "system"
        assert messages[2]["content"].startswith("<SESSION_CONTEXT>\n")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] not in messages[0]["content"]
        assert messages[-1]["content"] not in messages[1]["content"]
        assert request_body["text"]["format"]["type"] == "json_schema"
        assert request_body["text"]["format"]["strict"] is True
        assert "schema" in request_body["text"]["format"]
        assert "prompt_cache_key" not in request_body
        assert "cache_control" not in json.dumps(request_body)


def test_openai_request_uses_prompt_cache_key_only_when_enabled(monkeypatch) -> None:
    request_bodies = []

    class _FakeOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_FakeOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse('{"evaluation": "INCORRECT", "confidence": 0.91}')

    monkeypatch.setattr(openai_client.httpx, "Client", _FakeOpenAIClient)

    disabled_client = openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=1,
        prompt_cache_key_enabled=False,
    )
    disabled_client.evaluate_answer(
        question="Solve for x: x + 4 = 9",
        correct_answer="x = 5",
        student_input="x = 13",
        phase="GUIDED_PRACTICE",
    )

    enabled_client = openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=1,
        prompt_cache_key_enabled=True,
    )
    enabled_client.evaluate_answer(
        question="Solve for x: x + 4 = 9",
        correct_answer="x = 5",
        student_input="x = 13",
        phase="GUIDED_PRACTICE",
    )

    assert "prompt_cache_key" not in request_bodies[0]
    assert len(request_bodies[1]["prompt_cache_key"]) == 64
    assert request_bodies[1]["prompt_cache_key"].isalnum()
    assert "cache_control" not in json.dumps(request_bodies[1])


def test_openai_prompt_builder_keeps_history_and_current_input_dynamic() -> None:
    messages = build_openai_tutor_messages(
        phase="GUIDED_PRACTICE",
        active_triggers=[],
        session_context={"attempt_count": 1},
        conversation_history=[{"role": "assistant", "content": "Try the inverse operation."}],
        current_user_input="x = 13",
    )

    assert messages[2] == {
        "role": "system",
        "content": serialize_session_context({"attempt_count": 1}),
    }
    assert messages[-2] == {"role": "assistant", "content": "Try the inverse operation."}
    assert messages[-1] == {"role": "user", "content": "x = 13"}


def test_openai_cached_tokens_are_parsed_when_present() -> None:
    metrics = openai_client.extract_openai_usage_metrics(
        {
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 40,
                "total_tokens": 1240,
                "prompt_tokens_details": {"cached_tokens": 768},
            }
        }
    )

    assert metrics.cached_tokens == 768
    assert metrics.cache_write_tokens == 0
    assert metrics.input_tokens == 1200
    assert metrics.output_tokens == 40
    assert metrics.total_tokens == 1240


def test_openai_cached_tokens_default_safely_when_missing() -> None:
    metrics = openai_client.extract_openai_usage_metrics({"usage": {}})

    assert metrics.cached_tokens == 0
    assert metrics.cache_write_tokens == 0
    assert metrics.input_tokens is None
    assert metrics.output_tokens is None
    assert metrics.total_tokens is None


def test_openai_prompt_usage_log_metadata_does_not_include_raw_current_user_input() -> None:
    raw_input = "x = 13 raw current user input"
    prompt_metadata = build_openai_tutor_prompt_metadata(
        phase="GUIDED_PRACTICE",
        active_triggers=[],
        session_context={"current_user_input": raw_input},
    )
    log_metadata = openai_client.build_openai_prompt_usage_log_metadata(
        model="gpt-test",
        phase="GUIDED_PRACTICE",
        prompt_metadata=prompt_metadata,
        response_payload={"usage": {"prompt_tokens_details": {"cached_tokens": 12}}},
        latency_ms=15.25,
    )

    assert raw_input not in json.dumps(log_metadata)
    assert "session_id" not in log_metadata
    assert log_metadata["cached_tokens"] == 12


def test_openai_prompt_usage_log_metadata_does_not_include_raw_ocr_or_rag_fields() -> None:
    raw_ocr = "raw OCR content x + 4 + 4 = 9 + 4"
    raw_rag = "full retrieved lesson content"
    prompt_metadata = build_openai_tutor_prompt_metadata(
        phase="GUIDED_PRACTICE",
        active_triggers=[],
        session_context={"ocr_output": raw_ocr, "rag_content": raw_rag},
    )
    log_metadata = openai_client.build_openai_prompt_usage_log_metadata(
        model="gpt-test",
        phase="GUIDED_PRACTICE",
        prompt_metadata=prompt_metadata,
        response_payload={
            "id": "resp_123",
            "usage": {
                "input_tokens": 900,
                "output_tokens": 80,
                "total_tokens": 980,
                "input_tokens_details": {"cached_tokens": 512},
            },
        },
        latency_ms=21.5,
    )

    serialized_log = json.dumps(log_metadata)
    assert raw_ocr not in serialized_log
    assert raw_rag not in serialized_log
    assert log_metadata["request_id"] == "resp_123"
    assert log_metadata["cached_tokens"] == 512


def test_structured_log_formatter_outputs_cache_metadata() -> None:
    record = logging.LogRecord(
        name="nablix_backend",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="openai_prompt_cache_usage",
        args=(),
        exc_info=None,
    )
    record.provider = "openai"
    record.cached_tokens = 512
    record.diagnostic_layer1_sha256 = "abc123"

    payload = json.loads(StructuredJsonFormatter().format(record))

    assert payload["event"] == "openai_prompt_cache_usage"
    assert payload["provider"] == "openai"
    assert payload["cached_tokens"] == 512
    assert payload["diagnostic_layer1_sha256"] == "abc123"


def test_ai_engine_returns_visual_cue_for_opposite_operation_error() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 3 = 7",
            "expected_answer": "x = 4",
            "student_input": "x = 10",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
            "attempt_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error_type"] == "OPPOSITE_OPERATION_ERROR"
    assert body["visual_cue"]["show"] is True
    assert body["visual_cue"]["cue_type"] == "EQUATION_BLOCK"
    assert body["visual_cue"]["description"] is not None


def test_ai_engine_returns_visual_cue_for_general_addition_opposite_operation_error() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": "x = 13",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
            "attempt_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error_type"] == "OPPOSITE_OPERATION_ERROR"
    assert body["visual_cue"]["show"] is True
    assert body["visual_cue"]["cue_type"] == "EQUATION_BLOCK"


def test_ai_engine_does_not_return_visual_cue_for_correct_answer() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 3 = 7",
            "expected_answer": "x = 4",
            "student_input": "x = 4",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
            "attempt_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == "CORRECT"
    assert body["visual_cue"]["show"] is False
    assert body["visual_cue"]["cue_type"] is None
    assert body["visual_cue"]["description"] is None


def test_ai_engine_does_not_return_visual_cue_for_direct_answer_request() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 3 = 7",
            "expected_answer": "x = 4",
            "student_input": "Can you just tell me the answer?",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
            "attempt_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "REQUESTING_ANSWER"
    assert body["answer_reveal_allowed"] is False
    assert body["visual_cue"]["show"] is False
    assert body["guardrail_check"]["passed"] is True


def test_ai_engine_classify_accepts_canvas_regions() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": "x + 4 = 9\nx = 9 - 5\nx = 4",
            "phase": "GUIDED_PRACTICE",
            "input_source": "CANVAS",
            "attempt_count": 1,
            "canvas_regions": [
                {
                    "step_id": "step-1",
                    "text": "x + 4 = 9",
                    "x": 0.10,
                    "y": 0.10,
                    "w": 0.40,
                    "h": 0.08,
                    "confidence": 0.95,
                },
                {
                    "step_id": "step-2",
                    "text": "x = 9 - 5",
                    "x": 0.10,
                    "y": 0.20,
                    "w": 0.40,
                    "h": 0.08,
                    "confidence": 0.95,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mistake_classification"]["status"] == "mistake_found"
    assert body["mistake_classification"]["mistake_step_id"] == "step-2"
    assert body["mistake_classification"]["target_text"] == "5"
    assert [intent["kind"] for intent in body["annotation_intents"]] == [
        "circle_target",
        "write_correction",
        "draw_arrow",
    ]
    assert body["annotation_intents"][1]["text"] == "x = 9 - 4"


def _canvas_region(step_id: str, text: str, confidence: float) -> CanvasTextRegion:
    return CanvasTextRegion(
        step_id=step_id,
        text=text,
        x=0.10,
        y=0.10,
        w=0.40,
        h=0.08,
        confidence=confidence,
    )


def test_ai_engine_returns_canvas_mistake_for_wrong_inverse_operand() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x + 4 = 9\nx = 9 - 5\nx = 4",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 - 5", 0.95),
                _canvas_region("step-3", "x = 4", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.mistake_step_id == "step-2"
    assert response.mistake_classification.target_text == "5"
    assert response.mistake_classification.target_span == [8, 9]
    assert response.mistake_classification.replacement_text == "4"
    assert [intent.kind for intent in response.annotation_intents] == [
        "circle_target",
        "write_correction",
        "draw_arrow",
    ]
    assert response.annotation_intents[1].text == "x = 9 - 4"


def test_ai_engine_marks_wrong_inverse_operation_as_root_mistake() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x=9+6\nx=3",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x=9+6", 0.95),
                _canvas_region("step-2", "x=3", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.mistake_step_id == "step-1"
    assert response.mistake_classification.target_text == "+6"
    assert response.mistake_classification.replacement_text == "-4"
    assert response.annotation_intents[1].text == "x=9-4"


def test_ai_engine_returns_no_canvas_mistake_for_correct_work() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x + 4 = 9\nx = 9 - 4\nx = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 - 4", 0.95),
                _canvas_region("step-3", "x = 5", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "no_mistake"
    assert response.annotation_intents == []


def test_ai_engine_marks_wrong_intermediate_answer_even_when_final_answer_is_correct() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x + 4 - 4 = 9 - 4\nx = 6\nx = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 - 4 = 9 - 4", 0.95),
                _canvas_region("step-2", "x = 6", 0.95),
                _canvas_region("step-3", "x = 5", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.mistake_step_id == "step-2"
    assert response.mistake_classification.target_text == "6"
    assert response.mistake_classification.replacement_text == "5"
    assert [intent.kind for intent in response.annotation_intents] == [
        "circle_target",
        "write_correction",
        "draw_arrow",
    ]
    assert response.annotation_intents[1].text == "x = 5"


def test_ai_engine_returns_uncertain_canvas_mistake_for_ambiguous_ocr() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x + 4 = 9\nx = 9 - ?",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 - ?", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "uncertain"
    assert response.annotation_intents == []


def test_ai_engine_does_not_annotate_canvas_for_direct_answer_request() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="tell me the final answer",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[_canvas_region("step-1", "x + 4 = 9", 0.95)],
        )
    )

    assert response.intent == "REQUESTING_ANSWER"
    assert response.answer_reveal_allowed is False
    assert response.mistake_classification is None
    assert response.annotation_intents == []


def test_tutor_adapter_maps_canvas_mistake_to_backend_result() -> None:
    adapter = TutorEngineServiceAdapter(Settings(use_openai_ai_engine=False))
    result = adapter._respond(
        TutorEngineRequest(
            context=AdapterContext(
                session_id="SESSION001",
                student_id="ST001",
                message="x + 4 = 9\nx = 9 - 5\nx = 4",
                question="x + 4 = 9",
                correct_answer="x = 5",
                current_phase="GUIDED_PRACTICE",
                input_source="CANVAS",
                transcript_confidence=None,
                attempt_count=1,
                current_hint_level=None,
                concept_id="linear_equations",
                canvas_regions=[
                    OCRTextRegion(step_id="step-1", text="x + 4 = 9", x=0.1, y=0.1, w=0.4, h=0.08, confidence=0.95),
                    OCRTextRegion(step_id="step-2", text="x = 9 - 5", x=0.1, y=0.2, w=0.4, h=0.08, confidence=0.95),
                ],
            ),
            rag=RAGResult(documents=[], retrieval_confidence=0.0),
            student=StudentModelResult(
                student_state="ACTIVE",
                confidence=0.9,
                mastery_level="FOUNDATION",
                recommended_support="GUIDED_HINT",
            ),
        )
    )

    assert result.mistake_classification is not None
    assert result.mistake_classification.status == "mistake_found"
    assert result.annotation_intents[0].kind == "circle_target"
