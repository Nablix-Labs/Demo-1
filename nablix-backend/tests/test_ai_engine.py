from fastapi.testclient import TestClient

from app.ai_engine import openai_client
from app.core.config import get_settings
from app.main import app


client = TestClient(app)


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
