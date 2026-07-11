from fastapi.testclient import TestClient
import pytest

from app.adapters.tutor_engine import TutorEngineServiceAdapter
from app.ai_engine import openai_client
from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.ai_engine.schemas import CanvasTextRegion
from app.core.config import Settings, get_settings
from app.main import app
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


class _FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.status_code = 200
        self.text = content
        self._content = content

    def json(self) -> dict[str, str]:
        return {"output_text": self._content}


def test_ai_engine_can_use_openai_when_feature_flag_is_enabled(monkeypatch) -> None:
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
            return responses.pop(0)

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NABLIX_OPENAI_AI_ENGINE_MODEL", "gpt-test")
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
