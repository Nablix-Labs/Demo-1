import json
import logging

from fastapi.testclient import TestClient
import pytest

from app.adapters.tutor_engine import TutorEngineServiceAdapter, apply_retrieved_content
from app.ai_engine import classifier, openai_client
from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.ai_engine.prompt_registry import (
    Trigger,
    build_openai_tutor_messages,
    build_openai_tutor_prompt_metadata,
    load_prompt_registry,
    serialize_session_context,
)
from app.ai_engine.schemas import CanvasTextRegion
from app.core.config import Settings, get_settings
from app.core.exceptions import AdapterError
from app.core.logger import StructuredJsonFormatter
from app.main import app, prompt_registry as startup_prompt_registry
from app.models.adapters import (
    AdapterContext,
    ConversationMessage,
    ConversationState,
    OCRTextRegion,
    Phase2PromptContext,
    RAGResult,
    RetrievedDocument,
    StudentModelResult,
    TutorEngineRequest,
)
from app.models.student_model_session import AnswerSpec
from app.models.guided_learning import (
    ActiveTeachingObjective,
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedEvaluation,
    ScaffoldEvaluationContext,
    ScaffoldStepEvaluation,
)


client = TestClient(app)


def _guided_context(stuck_count: int) -> Phase2PromptContext:
    return Phase2PromptContext(
        target_micro_skill_ids=["T02.M8"],
        support_state={},
        potential_errors=[
            {
                "error_code": "ERR-T02-ADDITION",
                "description": "Interprets adjacent terms as addition.",
                "response_patterns": ["c + d"],
            }
        ],
        support_catalog={"hints": [{"hint_id": "PRIVATE-FUTURE-HINT"}]},
        current_support=None,
        current_scaffold_step_number=0,
        consecutive_stuck_count=stuck_count,
    )


def _guided_rubric() -> GeneratedQuestionRubric:
    return GeneratedQuestionRubric(
        question_id="Q-T02-002",
        required_concepts=[
            GeneratedConcept(
                concept_id="OPERATION",
                description="Recognises multiplication.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="EXPANDED_MEANING",
                description="Expands adjacent letters.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="rubric-hash",
        prompt_version="1.0.0",
    )


def _answer_spec(
    canonical_answer: str,
    accepted_answers: list[str],
    verification_method: str,
) -> AnswerSpec:
    return AnswerSpec(
        answer_spec_id="ANS-TEST",
        canonical_answer=canonical_answer,
        accepted_answers=accepted_answers,
        verification_method=verification_method,
    )


@pytest.fixture(autouse=True)
def disable_openai_ai_engine_by_default(monkeypatch):
    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "false")
    monkeypatch.delenv("NABLIX_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_exact_notation_match_accepts_caret_exponent_and_cannot_be_overridden(
    monkeypatch,
) -> None:
    class _ContradictingOpenAIClient:
        def generate_tutor_turn(self, **kwargs):
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="INCORRECT",
                error_type="NOTATION_ISSUE",
                response_strategy="GUIDED_HINT",
                hint_level=1,
                tutor_message="There is a spacing problem.",
                tutor_message_voice_optimised="There is a spacing problem.",
                reasoning_complete=False,
                confidence=0.91,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ContradictingOpenAIClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question="Write p × p × q in compact algebraic notation.",
            correct_answer="p²q",
            answer_spec=_answer_spec(
                canonical_answer="p²q",
                accepted_answers=["p²q", "p^2q"],
                verification_method="EXACT_NOTATION_MATCH",
            ),
            student_input="p^2q",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.question_completed is True
    assert response.tutor_message == "Correct. Nice work explaining your answer."


@pytest.mark.parametrize(
    ("student_input", "canonical_answer", "accepted_answers"),
    [
        (
            "1/2 is multiplying x, so it's 1/2x",
            "½x",
            ["½x", "(1/2)x"],
        ),
        ("I think the answer is p squared, so p^2q.", "p²q", ["p^2q"]),
        ("The compact expression is 4y.", "4y", ["4y"]),
    ],
)
def test_exact_notation_match_accepts_notation_inside_spoken_response(
    student_input: str,
    canonical_answer: str,
    accepted_answers: list[str],
) -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Write the expression in compact notation.",
            correct_answer=canonical_answer,
            answer_spec=_answer_spec(
                canonical_answer=canonical_answer,
                accepted_answers=accepted_answers,
                verification_method="EXACT_NOTATION_MATCH",
            ),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.95,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.question_completed is True


@pytest.mark.parametrize(
    "student_input",
    [
        "I think it might be 1/2 + x.",
        "The answer is x minus 1/2.",
        "I can see 1/2, but I do not know the answer.",
    ],
)
def test_exact_notation_match_rejects_wrong_or_incomplete_spoken_response(
    student_input: str,
) -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Write one half times x in compact notation.",
            correct_answer="½x",
            answer_spec=_answer_spec(
                canonical_answer="½x",
                accepted_answers=["½x", "(1/2)x"],
                verification_method="EXACT_NOTATION_MATCH",
            ),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.95,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation != "CORRECT"
    assert response.question_completed is False


def test_symbolic_equivalence_accepts_reordered_addition() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Write the general rule.",
            correct_answer="n + 5",
            answer_spec=_answer_spec(
                canonical_answer="n + 5",
                accepted_answers=["n+5", "5+n"],
                verification_method="SYMBOLIC_EQUIVALENCE",
            ),
            student_input="5 + n",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.question_completed is True


def test_semantic_verification_sends_full_answer_spec_to_llm(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _SemanticOpenAIClient:
        def generate_tutor_turn(self, **kwargs):
            captured.update(kwargs)
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="PARTIALLY_CORRECT",
                error_type="INSUFFICIENT_INFORMATION",
                response_strategy="GUIDED_HINT",
                hint_level=1,
                tutor_message=(
                    "You identified the counters. Does n mean the counters "
                    "themselves or their number?"
                ),
                tutor_message_voice_optimised=(
                    "You identified the counters. Does n mean the counters "
                    "themselves or their number?"
                ),
                reasoning_complete=False,
                confidence=0.93,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _SemanticOpenAIClient(),
    )
    answer_spec = _answer_spec(
        canonical_answer="The number of additional counters.",
        accepted_answers=[
            "number of additional counters",
            "how many counters are added",
        ],
        verification_method="CONCEPT_TEXT_MATCH",
    )
    phase_2_context = Phase2PromptContext(
        target_micro_skill_ids=["T02.M8"],
        support_state={"highest_support_used_by_skill": {"T02.M8": "HINT"}},
        potential_errors=[{"error_code": "VARIABLE_MEANING_INCOMPLETE"}],
        support_catalog={"hints": [{"hint_id": "H-T02-M8-01"}]},
        current_support={"support_type": "HINT"},
        current_scaffold_step_number=0,
        consecutive_stuck_count=0,
    )
    response = classify_student_response(
        ClassificationRequest(
            question="In Total = n + 4, what does n represent?",
            correct_answer=answer_spec.canonical_answer,
            answer_spec=answer_spec,
            phase_2_prompt_context=phase_2_context,
            student_input="the counters",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert captured["answer_spec"] == answer_spec
    assert captured["phase_2_prompt_context"] == phase_2_context
    assert response.evaluation == "PARTIALLY_CORRECT"
    assert response.tutor_message.startswith("You identified the counters.")


def test_protocol_triggers_are_derived_from_input_confidence() -> None:
    rules = classifier.load_classifier_rules()
    voice_request = ClassificationRequest(
        question="Solve x + 4 = 9.",
        correct_answer="x = 5",
        student_input="x maybe five",
        current_phase="GUIDED_PRACTICE",
        input_source="VOICE",
        transcript_confidence=0.2,
        attempt_count=1,
        current_hint_level=None,
    )
    canvas_request = voice_request.model_copy(
        update={
            "input_source": "CANVAS",
            "transcript_confidence": None,
            "canvas_regions": [
                CanvasTextRegion(
                    step_id="step-1",
                    text="x + 4",
                    x=0.1,
                    y=0.1,
                    w=0.2,
                    h=0.1,
                    confidence=0.1,
                )
            ],
        }
    )

    assert classifier.detect_protocol_triggers(voice_request, rules) == [
        Trigger.VOICE_AMBIGUITY
    ]
    assert classifier.detect_protocol_triggers(canvas_request, rules) == [
        Trigger.HANDWRITING_AMBIGUITY
    ]


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


def test_ai_engine_api_accepts_contextual_conversation_state() -> None:
    response = client.post(
        "/ai-engine/classify",
        json={
            "student_input": "Right.",
            "current_phase": "GUIDED_PRACTICE",
            "question": "Solve for x: x + 4 = 9",
            "correct_answer": "x = 5",
            "input_source": "VOICE",
            "transcript_confidence": 0.98,
            "attempt_count": 1,
            "question_completed": True,
            "conversation_history": [
                {
                    "role": "assistant",
                    "content": "Correct. Nice work explaining your answer.",
                }
            ],
            "conversation_state": {
                "last_tutor_action": "CONFIRMED_CORRECT_ANSWER",
                "expected_student_response": "ACKNOWLEDGEMENT_OR_CONTINUE",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "ACKNOWLEDGEMENT"
    assert body["attempt_increment"] == 0
    assert body["recommended_conversation_action"] == "ADVANCE_TO_NEXT_QUESTION"
    assert body["student_model_events"] == []


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
        _FakeOpenAIResponse(
            '{"intent":"SUBMITTING_ANSWER","evaluation":"PARTIALLY_CORRECT",'
            '"error_type":"ARITHMETIC_ERROR","response_strategy":"GUIDED_HINT",'
            '"hint_level":1,"tutor_message": "Check the inverse operation first.", '
            '"tutor_message_voice_optimised": "Check the inverse operation first.", '
            '"reasoning_complete":false,"confidence": 0.86}'
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
    assert len(request_bodies) == 1

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
        assert request_body["store"] is False
        assert "schema" in request_body["text"]["format"]
        assert "prompt_cache_key" not in request_body
        assert "cache_control" not in json.dumps(request_body)
    user_payload = json.loads(request_bodies[0]["input"][-1]["content"])
    assert user_payload["component"] == "tutor_turn"
    assert user_payload["correct_answer"] == "x = 4"
    assert user_payload["attempt_count"] == 1
    assert user_payload["answer_reveal_allowed"] is False


def test_canvas_math_decision_uses_openai_wording_without_exposing_answer(monkeypatch) -> None:
    request_bodies: list[dict[str, object]] = []

    class _CanvasMessageOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_CanvasMessageOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse(
                '{"tutor_message":"Your operation on both sides is correct. '
                'Recheck the subtraction before writing the value of x.",'
                '"tutor_message_voice_optimised":"Your operation on both sides is correct. '
                'Recheck the subtraction before writing the value of x.",'
                '"confidence":0.94}'
            )

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_client.httpx, "Client", _CanvasMessageOpenAIClient)
    get_settings.cache_clear()

    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "Solve for x: x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": "x + 4 - 4 = 9 - 4\nx = 10",
            "phase": "GUIDED_PRACTICE",
            "input_source": "CANVAS",
            "attempt_count": 2,
            "canvas_regions": [
                {
                    "step_id": "step-1",
                    "text": "x + 4 - 4 = 9 - 4",
                    "x": 0.1,
                    "y": 0.2,
                    "w": 0.7,
                    "h": 0.1,
                    "confidence": 0.99,
                },
                {
                    "step_id": "step-2",
                    "text": "x = 10",
                    "x": 0.1,
                    "y": 0.4,
                    "w": 0.3,
                    "h": 0.1,
                    "confidence": 0.99,
                },
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error_type"] == "ARITHMETIC_ERROR"
    assert body["mistake_classification"]["mistake_step_id"] == "step-2"
    assert body["tutor_message"] == (
        "Your operation on both sides is correct. "
        "Recheck the subtraction before writing the value of x."
    )
    assert len(request_bodies) == 1
    user_payload = json.loads(request_bodies[0]["input"][-1]["content"])
    assert user_payload["component"] == "tutor_message"
    assert user_payload["error_type"] == "ARITHMETIC_ERROR"
    assert user_payload["canvas_context"]["previous_step"] == "x + 4 - 4 = 9 - 4"
    assert user_payload["canvas_context"]["incorrect_step"] == "x = 10"
    assert "correct_answer" not in user_payload


def test_deterministic_correct_answer_uses_one_openai_call_and_preserves_correct_result(monkeypatch) -> None:
    request_bodies = []

    class _CorrectAnswerOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_CorrectAnswerOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse(
                '{"intent":"SUBMITTING_ANSWER","evaluation":"INCORRECT",'
                '"error_type":"ARITHMETIC_ERROR","response_strategy":"GUIDED_HINT",'
                '"hint_level":1,"tutor_message":"Correct. Nice work explaining your answer.",'
                '"tutor_message_voice_optimised":"Correct. Nice work explaining your answer.",'
                '"reasoning_complete":false,'
                '"confidence":0.98}'
            )

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NABLIX_OPENAI_PROMPT_CACHE_KEY_ENABLED", "false")
    monkeypatch.setattr(openai_client.httpx, "Client", _CorrectAnswerOpenAIClient)
    get_settings.cache_clear()

    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": "x = 5",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
            "attempt_count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == "PARTIALLY_CORRECT"
    assert body["tutor_message"] == "Your value is correct. How did you work it out?"
    assert body["answer_value_confirmed"] is True
    assert body["reasoning_complete"] is False
    assert body["question_completed"] is False
    assert body["guardrail_check"]["passed"] is True
    assert len(request_bodies) == 1


@pytest.mark.parametrize(
    "student_input",
    ["five", "x equals five", "x is equal to five", "x is equals to five"],
)
def test_natural_language_correct_answer_uses_one_openai_turn_and_safe_confirmation(
    monkeypatch,
    student_input: str,
) -> None:
    request_bodies: list[dict[str, object]] = []

    class _NaturalAnswerOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_NaturalAnswerOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse(
                '{"intent":"EXPRESSING_CONFUSION","evaluation":"PARTIALLY_CORRECT",'
                '"error_type":"CONCEPTUAL_MISUNDERSTANDING",'
                '"response_strategy":"CLARIFY","hint_level":null,'
                '"tutor_message":"Correct. Nice work explaining your answer.",'
                '"tutor_message_voice_optimised":"Correct. Nice work explaining your answer.",'
                '"reasoning_complete":false,'
                '"confidence":0.98}'
            )

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_client.httpx, "Client", _NaturalAnswerOpenAIClient)
    get_settings.cache_clear()

    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": student_input,
            "phase": "GUIDED_PRACTICE",
            "input_source": "VOICE",
            "transcript_confidence": 0.96,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == "PARTIALLY_CORRECT"
    assert body["intent"] == "SUBMITTING_ANSWER"
    assert body["error_type"] == "INSUFFICIENT_INFORMATION"
    assert body["response_strategy"] == "CLARIFY"
    assert body["tutor_message"] == "Your value is correct. How did you work it out?"
    assert body["recommended_conversation_action"] == "REQUEST_EXPLANATION"
    assert body["question_completed"] is False
    assert body["guardrail_check"]["passed"] is True
    assert len(request_bodies) == 1
    user_payload = json.loads(request_bodies[0]["input"][-1]["content"])
    assert user_payload["grounded_intent"] == "SUBMITTING_ANSWER"
    assert user_payload["grounded_evaluation"] == "CORRECT"
    assert user_payload["grounded_error_type"] is None


def test_unified_openai_turn_cannot_reveal_answer_for_incorrect_attempt(monkeypatch) -> None:
    request_bodies: list[dict[str, object]] = []

    class _RevealingOpenAIClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_RevealingOpenAIClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse(
                '{"intent":"SUBMITTING_ANSWER","evaluation":"INCORRECT",'
                '"error_type":"ARITHMETIC_ERROR","response_strategy":"GUIDED_HINT",'
                '"hint_level":1,"tutor_message":"The answer is x = 5.",'
                '"tutor_message_voice_optimised":"The answer is x equals 5.",'
                '"reasoning_complete":false,"confidence":0.93}'
            )

    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "true")
    monkeypatch.setenv("NABLIX_OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_client.httpx, "Client", _RevealingOpenAIClient)
    get_settings.cache_clear()

    response = client.post(
        "/ai-engine/classify",
        json={
            "question_context": "x + 4 = 9",
            "expected_answer": "x = 5",
            "student_input": "x = 10",
            "phase": "GUIDED_PRACTICE",
            "input_source": "TEXT",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation"] == "INCORRECT"
    assert body["tutor_message"] == "I cannot give the final answer, but I can help you with the next step."
    assert body["guardrail_check"]["passed"] is False
    assert len(request_bodies) == 1


def test_low_confidence_voice_input_skips_openai_tutor_turn(monkeypatch) -> None:
    class _UnexpectedOpenAIClient:
        def generate_tutor_turn(self, **kwargs) -> openai_client.OpenAITutorTurn:
            raise AssertionError("Low-confidence voice input must not call OpenAI.")

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _UnexpectedOpenAIClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="x might be thirteen",
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.2,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "UNCLEAR"
    assert response.response_strategy == "CLARIFY"
    assert response.tutor_message == "I could not read that clearly. Please try saying or typing your answer again."


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
            return _FakeOpenAIResponse(
                '{"intent":"SUBMITTING_ANSWER","evaluation":"INCORRECT",'
                '"error_type":"ARITHMETIC_ERROR","response_strategy":"GUIDED_HINT",'
                '"hint_level":1,"tutor_message":"Check your arithmetic.",'
                '"tutor_message_voice_optimised":"Check your arithmetic.",'
                '"reasoning_complete":false,"confidence":0.91}'
            )

    monkeypatch.setattr(openai_client.httpx, "Client", _FakeOpenAIClient)

    disabled_client = openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=1,
        prompt_cache_key_enabled=False,
        store_responses=False,
        retry_count=0,
    )
    disabled_client.generate_tutor_turn(
        question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            answer_spec=None,
            phase_2_prompt_context=None,
            active_triggers=[],
        student_input="x = 13",
        phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
        question_completed=False,
        answer_value_confirmed=False,
        reasoning_required=True,
        grounded_intent="SUBMITTING_ANSWER",
        grounded_evaluation="INCORRECT",
        grounded_error_type="ARITHMETIC_ERROR",
        conversation_history=[],
        conversation_state=None,
    )

    enabled_client = openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=1,
        prompt_cache_key_enabled=True,
        store_responses=True,
        retry_count=0,
    )
    enabled_client.generate_tutor_turn(
        question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            answer_spec=None,
            phase_2_prompt_context=None,
            active_triggers=[],
        student_input="x = 13",
        phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
        question_completed=False,
        answer_value_confirmed=False,
        reasoning_required=True,
        grounded_intent="SUBMITTING_ANSWER",
        grounded_evaluation="INCORRECT",
        grounded_error_type="ARITHMETIC_ERROR",
        conversation_history=[
            ConversationMessage(role="assistant", content="Try the inverse operation.")
        ],
        conversation_state=ConversationState(
            last_tutor_action="ASKED_QUESTION",
            expected_student_response="EXPLANATION",
        ),
    )

    assert "prompt_cache_key" not in request_bodies[0]
    assert request_bodies[0]["store"] is False
    assert len(request_bodies[1]["prompt_cache_key"]) == 64
    assert request_bodies[1]["prompt_cache_key"].isalnum()
    assert request_bodies[1]["store"] is True
    assert "cache_control" not in json.dumps(request_bodies[1])
    assert request_bodies[1]["input"][3] == {
        "role": "assistant",
        "content": "Try the inverse operation.",
    }
    serialized_context: str = request_bodies[1]["input"][2]["content"]
    assert '"expected_student_response":"EXPLANATION"' in serialized_context


def test_deterministic_correct_result_cannot_be_downgraded_by_openai(monkeypatch) -> None:
    class _IncorrectOpenAIClient:
        def generate_tutor_turn(self, **kwargs) -> openai_client.OpenAITutorTurn:
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="INCORRECT",
                error_type="ARITHMETIC_ERROR",
                response_strategy="GUIDED_HINT",
                hint_level=1,
                tutor_message="Correct. Nice work explaining your answer.",
                tutor_message_voice_optimised="Correct. Nice work explaining your answer.",
                reasoning_complete=False,
                confidence=0.98,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _IncorrectOpenAIClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="x = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.95,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "PARTIALLY_CORRECT"
    assert response.tutor_message == "Your value is correct. How did you work it out?"
    assert response.answer_value_confirmed is True
    assert response.question_completed is False


def test_correct_answer_acknowledgement_is_sanitized_without_refusal(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier,
        "build_tutor_message",
        lambda *args: "Correct, x = 5.",
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="x = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "PARTIALLY_CORRECT"
    assert response.tutor_message == "Your value is correct. How did you work it out?"
    assert response.answer_value_confirmed is True
    assert response.question_completed is False
    assert response.guardrail_check.passed is True


def test_correct_value_requires_reasoning_before_question_completion() -> None:
    value_response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="x = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert value_response.answer_value_confirmed is True
    assert value_response.reasoning_complete is False
    assert value_response.question_completed is False
    assert value_response.recommended_conversation_action == "REQUEST_EXPLANATION"
    assert value_response.student_model_events == []


def test_correct_value_with_reasoning_completes_question() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="I subtracted 4 from both sides, so x = 5.",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.answer_value_confirmed is True
    assert response.reasoning_complete is True
    assert response.question_completed is True
    assert response.tutor_message == "Thanks for explaining your method. Let us continue."
    assert response.student_model_events[0].event_type == "CORRECT_ATTEMPT"


def test_follow_up_reasoning_completes_previously_confirmed_answer() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="I subtracted 4 from both sides because that isolates x.",
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.96,
            attempt_count=1,
            current_hint_level=None,
            answer_value_confirmed=True,
            conversation_state=ConversationState(
                last_tutor_action="REQUESTED_EXPLANATION",
                expected_student_response="EXPLANATION",
            ),
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.reasoning_complete is True
    assert response.question_completed is True
    assert response.attempt_increment == 0
    assert response.tutor_message == "Thanks for explaining your method. Let us continue."


@pytest.mark.parametrize(
    ("attempt_count", "expected_strategy", "expected_hint_level"),
    [
        (1, "GUIDED_HINT", 1),
        (2, "GUIDED_HINT", 2),
        (3, "SCAFFOLD", None),
        (4, "PROVIDE_WORKED_EXAMPLE", None),
    ],
)
def test_repeated_confusion_progresses_guided_support(
    attempt_count: int,
    expected_strategy: str,
    expected_hint_level: int | None,
) -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Write p × p × q in compact algebraic notation.",
            correct_answer="p²q",
            student_input="I don't know",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=attempt_count,
            current_hint_level=None,
        )
    )

    assert response.intent == "EXPRESSING_CONFUSION"
    assert response.evaluation == "NO_ATTEMPT"
    assert response.response_strategy == expected_strategy
    assert response.hint_level == expected_hint_level
    assert response.attempt_increment == 0


def test_explicit_confusion_intent_cannot_be_overridden_by_openai(
    monkeypatch,
) -> None:
    class _ContradictingOpenAIClient:
        def generate_tutor_turn(self, **kwargs) -> openai_client.OpenAITutorTurn:
            assert kwargs["grounded_intent"] == "EXPRESSING_CONFUSION"
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="INCORRECT",
                error_type="UNKNOWN_ERROR",
                response_strategy="GUIDED_HINT",
                hint_level=2,
                tutor_message="Try another answer.",
                tutor_message_voice_optimised="Try another answer.",
                reasoning_complete=False,
                confidence=0.85,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ContradictingOpenAIClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Write ½ × x in compact notation.",
            correct_answer="½x",
            student_input="I am stuck",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=3,
            current_hint_level=None,
        )
    )

    assert response.intent == "EXPRESSING_CONFUSION"
    assert response.evaluation == "NO_ATTEMPT"
    assert response.response_strategy == "SCAFFOLD"
    assert response.attempt_increment == 0


def test_valid_worked_steps_override_incorrect_openai_reasoning_flag(monkeypatch) -> None:
    class _OpenAIClient:
        def generate_tutor_turn(self, **kwargs) -> openai_client.OpenAITutorTurn:
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="CORRECT",
                error_type=None,
                response_strategy="CONFIRM_CORRECT",
                hint_level=None,
                tutor_message="Thanks for showing your steps.",
                tutor_message_voice_optimised="Thanks for showing your steps.",
                reasoning_complete=False,
                confidence=0.95,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _OpenAIClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 6 = 10",
            correct_answer="x = 4",
            student_input="x + 6 - 6 = 10 - 6, so x = 4",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.reasoning_complete is True
    assert response.question_completed is True


def test_reasoning_accumulates_across_student_turns_for_current_question() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 6 = 10",
            correct_answer="x = 4",
            student_input="x = 4",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=2,
            current_hint_level=None,
            conversation_history=[
                ConversationMessage(
                    role="user",
                    content="x + 6 - 6 = 10 - 6",
                ),
                ConversationMessage(
                    role="assistant",
                    content="What is 10 minus 6?",
                ),
            ],
        )
    )

    assert response.answer_value_confirmed is True
    assert response.reasoning_complete is True
    assert response.question_completed is True
    assert response.tutor_message == "Thanks for explaining your method. Let us continue."


def test_partial_operation_explanation_receives_a_new_question() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 6 = 10",
            correct_answer="x = 4",
            student_input="I used subtraction.",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            answer_value_confirmed=True,
        )
    )

    assert response.question_completed is False
    assert response.tutor_message == "Why was that operation the right one for this equation?"


def test_contextual_acknowledgement_does_not_evaluate_or_emit_event(monkeypatch) -> None:
    class _UnexpectedOpenAIClient:
        def generate_tutor_turn(self, **kwargs) -> openai_client.OpenAITutorTurn:
            raise AssertionError("A known contextual acknowledgement must not call OpenAI.")

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _UnexpectedOpenAIClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="Right.",
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.98,
            attempt_count=1,
            question_completed=True,
            current_hint_level=None,
            conversation_history=[
                ConversationMessage(
                    role="assistant",
                    content="Correct. Nice work explaining your answer.",
                )
            ],
            conversation_state=ConversationState(
                last_tutor_action="CONFIRMED_CORRECT_ANSWER",
                expected_student_response="ACKNOWLEDGEMENT_OR_CONTINUE",
            ),
        )
    )

    assert response.intent == "ACKNOWLEDGEMENT"
    assert response.evaluation is None
    assert response.response_strategy == "CONTINUE"
    assert response.attempt_increment == 0
    assert response.question_completed is True
    assert response.recommended_conversation_action == "ADVANCE_TO_NEXT_QUESTION"
    assert response.student_model_events == []


def test_acknowledgement_word_is_not_contextual_without_expected_state() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="Solve for x: x + 4 = 9",
            correct_answer="x = 5",
            student_input="Right.",
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.98,
            attempt_count=1,
            question_completed=False,
            current_hint_level=None,
            conversation_state=ConversationState(
                last_tutor_action="ASKED_QUESTION",
                expected_student_response="ANSWER",
            ),
        )
    )

    assert response.intent != "ACKNOWLEDGEMENT"


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
    assert body["evaluation"] == "PARTIALLY_CORRECT"
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
    assert response.mistake_classification.replacement_text is None
    assert [intent.kind for intent in response.annotation_intents] == ["circle_target"]
    assert response.evaluation == "PARTIALLY_CORRECT"
    assert response.response_strategy == "GUIDED_HINT"


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


def test_canvas_math_review_accepts_subtraction_steps() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x - 4 = 9",
            correct_answer="x = 13",
            student_input="x - 4 = 9\nx = 9 + 4\nx = 13",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x - 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 + 4", 0.95),
                _canvas_region("step-3", "x = 13", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "no_mistake"
    assert [step.evaluation for step in response.canvas_feedback.step_feedback] == [
        "CORRECT",
        "CORRECT",
        "CORRECT",
    ]


def test_canvas_math_review_finds_first_multiplication_error() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="3x = 12",
            correct_answer="x = 4",
            student_input="3x = 12\nx = 12 * 3\nx = 36",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "3x = 12", 0.95),
                _canvas_region("step-2", "x = 12 * 3", 0.95),
                _canvas_region("step-3", "x = 36", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.mistake_step_id == "step-2"
    assert response.error_type == "CONCEPTUAL_MISUNDERSTANDING"
    assert response.canvas_feedback.highlight_instruction is not None
    assert response.canvas_feedback.highlight_instruction.step_number == 2
    assert [step.evaluation for step in response.canvas_feedback.step_feedback] == [
        "CORRECT",
        "INCORRECT",
        "INCORRECT",
    ]


def test_canvas_math_review_accepts_division_steps() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x / 3 = 5",
            correct_answer="x = 15",
            student_input="x / 3 = 5\nx = 5 * 3\nx = 15",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x / 3 = 5", 0.95),
                _canvas_region("step-2", "x = 5 * 3", 0.95),
                _canvas_region("step-3", "x = 15", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "no_mistake"


def test_canvas_math_review_rejects_unsupported_ocr_expression() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="sqrt(x) = 5",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[_canvas_region("step-1", "sqrt(x) = 5", 0.95)],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "uncertain"
    assert response.canvas_feedback.has_feedback is False
    assert response.annotation_intents == []


def test_canvas_math_review_suppresses_feedback_and_annotations_in_phase_3() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x = 9 + 4",
            current_phase="INDEPENDENT_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[_canvas_region("step-1", "x = 9 + 4", 0.95)],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.canvas_feedback.has_feedback is False
    assert response.annotation_intents == []


def test_canvas_math_review_marks_first_mistake_in_diagnostic_phase() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x = 9 - 4\nx = 4",
            current_phase="DIAGNOSTIC",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x = 9 - 4", 0.95),
                _canvas_region("step-2", "x = 4", 0.95),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.mistake_step_id == "step-2"
    assert response.canvas_feedback.has_feedback is True
    assert [intent.kind for intent in response.annotation_intents] == ["circle_target"]


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
                mastery_status="DEVELOPING",
                continuity_status="on_track",
                recommended_entry_phase="GUIDED_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=False,
            ),
        )
    )

    assert result.mistake_classification is not None
    assert result.mistake_classification.status == "mistake_found"
    assert result.annotation_intents[0].kind == "circle_target"
    assert result.canvas_feedback.has_feedback is True
    assert result.canvas_feedback.highlight_instruction is not None
    assert result.canvas_feedback.highlight_instruction.step_number == 2
    assert result.canvas_feedback.step_feedback[1].error_type == "ARITHMETIC_ERROR"


def test_retrieved_canvas_feedback_is_guarded_before_return() -> None:
    adapter = TutorEngineServiceAdapter(Settings(use_mock_tutor=True, use_openai_ai_engine=False))
    result = adapter._mock_response(
        TutorEngineRequest(
            context=AdapterContext(
                session_id="SESSION001",
                student_id="ST001",
                message="x = 6",
                question="x + 4 = 9",
                correct_answer="x = 5",
                current_phase="GUIDED_PRACTICE",
                input_source="CANVAS",
                attempt_count=1,
                canvas_regions=[
                    OCRTextRegion(
                        step_id="step-1",
                        text="x = 6",
                        x=0.1,
                        y=0.1,
                        w=0.3,
                        h=0.08,
                        confidence=0.95,
                    )
                ],
            ),
            rag=RAGResult(documents=[], retrieval_confidence=0.0),
            student=StudentModelResult(
                mastery_status="DEVELOPING",
                continuity_status="on_track",
                recommended_entry_phase="GUIDED_PRACTICE",
                hint_dependency_score=0.0,
                intervention_required=False,
            ),
        )
    )
    rag = RAGResult(
        documents=[
            RetrievedDocument(
                title="Unsafe hint",
                content="The answer is x = 5.",
                source="curriculum",
            )
        ],
        retrieval_confidence=0.99,
    )

    guarded = apply_retrieved_content(result, rag, "x = 5")

    assert guarded.tutor_message == "I cannot give the final answer, but I can help you with the next step."
    assert guarded.tutor_message_voice == guarded.tutor_message


def test_guided_llm_partial_persists_only_the_missing_objective(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            captured["rubric"] = kwargs
            return _guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["OPERATION"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["EXPANDED_MEANING"],
                selected_error_code=None,
                confidence=0.96,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["EXPANDED_MEANING"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["EXPANDED_MEANING"],
                ),
                tutor_message="Multiplication is the operation. What does cd expand to?",
                tutor_message_voice="Multiplication is the operation. What does c d expand to?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-002",
            question="What does cd mean?",
            correct_answer="c multiplied by d",
            answer_spec=_answer_spec(
                "c multiplied by d",
                ["c times d"],
                "CONCEPT_TEXT_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="multiplication",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "PARTIAL"
    assert response.student_model_events == []
    assert response.attempt_increment == 0
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.confirmed_concept_ids == ["OPERATION"]
    assert response.active_teaching_objective.missing_concept_ids == ["EXPANDED_MEANING"]
    rubric_payload = captured["rubric"]
    assert isinstance(rubric_payload, dict)
    assert rubric_payload["potential_errors"] == [
        {
            "error_code": "ERR-T02-ADDITION",
            "description": "Interprets adjacent terms as addition.",
        }
    ]


def test_guided_multipart_preserves_completed_parts_and_requests_the_missing_part(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule c + 4.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="CHANGING_VALUE",
                description="Identifies c as changing.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="FIXED_INCREMENT",
                description="Identifies +4 as fixed.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="multipart-rubric",
        prompt_version="1.0.0",
    )

    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            captured["rubric_question_type"] = kwargs["question_type"]
            return rubric

        def evaluate_guided_turn(self, **kwargs):
            captured["evaluation_question_type"] = kwargs["question_type"]
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["GENERAL_RULE", "CHANGING_VALUE"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["FIXED_INCREMENT"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["FIXED_INCREMENT"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["FIXED_INCREMENT"],
                ),
                tutor_message="Your rule and changing value are clear. What stays fixed?",
                tutor_message_voice="Your rule and changing value are clear. What stays fixed?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T01-006",
            question=(
                "A counter starts at any value c and increases by 4. "
                "Write the general rule and state what changes and what stays fixed."
            ),
            question_type="MULTI_PART_SHORT_RESPONSE",
            correct_answer="c + 4; c changes; +4 stays fixed",
            answer_spec=_answer_spec(
                "c + 4; c changes; +4 stays fixed",
                ["c+4", "c is changing", "add 4 stays fixed"],
                "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="The rule is c + 4 and c changes.",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert captured == {
        "rubric_question_type": "MULTI_PART_SHORT_RESPONSE",
        "evaluation_question_type": "MULTI_PART_SHORT_RESPONSE",
    }
    assert response.guided_student_state == "PARTIAL"
    assert response.student_model_events == []
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.confirmed_concept_ids == [
        "CHANGING_VALUE",
        "GENERAL_RULE",
    ]
    assert response.active_teaching_objective.missing_concept_ids == [
        "FIXED_INCREMENT"
    ]


def test_guided_multipart_rejects_completion_with_unconfirmed_required_parts(
    monkeypatch,
) -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule c + 4.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="CHANGING_VALUE",
                description="Identifies c as changing.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="FIXED_INCREMENT",
                description="Identifies +4 as fixed.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="multipart-rubric",
        prompt_version="1.0.0",
    )

    class _InvalidGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return rubric

        def evaluate_guided_turn(self, **kwargs):
            return GuidedEvaluation(
                student_state="CORRECT",
                newly_confirmed_concept_ids=["GENERAL_RULE"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=[],
                selected_error_code=None,
                confidence=0.98,
                next_objective=None,
                tutor_message="That completes the question.",
                tutor_message_voice="That completes the question.",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _InvalidGuidedClient(),
    )
    with pytest.raises(
        AdapterError,
        match="Multipart evaluation missing concepts do not match",
    ):
        classify_student_response(
            ClassificationRequest(
                question_id="Q-T01-006",
                question=(
                    "A counter starts at any value c and increases by 4. "
                    "Write the general rule and state what changes and what stays fixed."
                ),
                question_type="MULTI_PART_SHORT_RESPONSE",
                correct_answer="c + 4; c changes; +4 stays fixed",
                answer_spec=_answer_spec(
                    "c + 4; c changes; +4 stays fixed",
                    ["c+4", "c is changing", "add 4 stays fixed"],
                    "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
                ),
                phase_2_prompt_context=_guided_context(0),
                student_input="c + 4",
                current_phase="GUIDED_PRACTICE",
                input_source="TEXT",
                transcript_confidence=None,
                attempt_count=1,
                current_hint_level=None,
            )
        )


def test_guided_llm_repeated_stuck_requests_one_scaffold_escalation(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            objective = kwargs["active_objective"]
            return GuidedEvaluation(
                student_state="STUCK",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=objective.missing_concept_ids,
                selected_error_code=None,
                confidence=0.94,
                next_objective=objective,
                tutor_message="Let’s make it smaller. What operation joins c and d?",
                tutor_message_voice="Let’s make it smaller. What operation joins c and d?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-002",
            question="What does cd mean?",
            correct_answer="c multiplied by d",
            answer_spec=_answer_spec(
                "c multiplied by d",
                ["c times d"],
                "CONCEPT_TEXT_MATCH",
            ),
            phase_2_prompt_context=_guided_context(1),
            student_input="I don't know",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "STUCK"
    assert response.response_strategy == "SCAFFOLD"
    assert response.student_model_events == []
    assert response.attempt_increment == 0


def test_guided_exact_notation_stuck_uses_question_aware_llm_message(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric().model_copy(
                update={"question_id": "Q-T02-001"}
            )

        def evaluate_guided_turn(self, **kwargs):
            objective = kwargs["active_objective"]
            return GuidedEvaluation(
                student_state="STUCK",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=objective.missing_concept_ids,
                selected_error_code=None,
                confidence=0.95,
                next_objective=objective,
                tutor_message="Let’s make it smaller. Which letter is repeated?",
                tutor_message_voice="Let’s make it smaller. Which letter is repeated?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-001",
            question="Write y + y + y + y in compact algebraic notation.",
            correct_answer="4y",
            answer_spec=_answer_spec(
                "4y",
                ["4 × y"],
                "EXACT_NOTATION_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="I don't know",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "STUCK"
    assert response.tutor_message == (
        "Let’s make it smaller. Which letter is repeated?"
    )
    assert "x" not in response.tutor_message
    assert response.attempt_increment == 0


def test_guided_llm_wrong_uses_only_a_permitted_error_code(monkeypatch) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            return GuidedEvaluation(
                student_state="WRONG",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["OPERATION", "EXPANDED_MEANING"],
                selected_error_code="ERR-T02-ADDITION",
                confidence=0.97,
                next_objective=ActiveTeachingObjective(
                    objective_type="RECONSIDER_CONCEPT",
                    target_concept_ids=["OPERATION"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["OPERATION", "EXPANDED_MEANING"],
                ),
                tutor_message="Test that idea: does writing letters together mean adding?",
                tutor_message_voice="Test that idea: does writing letters together mean adding?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-002",
            question="What does cd mean?",
            correct_answer="c multiplied by d",
            answer_spec=_answer_spec(
                "c multiplied by d",
                ["c times d"],
                "CONCEPT_TEXT_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="c plus d",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "WRONG"
    assert response.selected_error_code == "ERR-T02-ADDITION"
    assert response.attempt_increment == 1


@pytest.mark.parametrize(
    "student_input",
    ["c x d", "c × d", "c*d", "c · d", "c times d", "c multiplied by d"],
)
def test_guided_concept_notation_equivalents_cannot_be_rejected_by_llm(
    monkeypatch,
    student_input: str,
) -> None:
    class _RejectingGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            raise AssertionError("An exact normalized match must not call the LLM.")

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _RejectingGuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-002",
            question="What does cd mean?",
            correct_answer="c multiplied by d",
            answer_spec=_answer_spec(
                "c multiplied by d",
                ["c times d", "c × d"],
                "CONCEPT_TEXT_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.question_completed is True


@pytest.mark.parametrize(
    ("student_input", "canonical_answer"),
    [
        ("p − 2", "p - 2"),
        ("6 / r", "6 ÷ r"),
        ("n equals 4", "n = 4"),
        ("6 * r", "6 × r"),
    ],
)
def test_semantic_contract_normalizes_general_keyboard_math_notation(
    student_input: str,
    canonical_answer: str,
) -> None:
    request = ClassificationRequest(
        question="Interpret the expression.",
        correct_answer=canonical_answer,
        answer_spec=_answer_spec(
            canonical_answer,
            [],
            "CONCEPT_TEXT_MATCH",
        ),
        student_input=student_input,
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )

    assert classifier.evaluate_answer_contract(request) == "CORRECT"


def test_multi_part_accepted_fragment_is_not_treated_as_complete(
    monkeypatch,
) -> None:
    class _PartialOpenAIClient:
        def generate_tutor_turn(self, **kwargs):
            return openai_client.OpenAITutorTurn(
                intent="SUBMITTING_ANSWER",
                evaluation="PARTIALLY_CORRECT",
                error_type="INSUFFICIENT_INFORMATION",
                response_strategy="GUIDED_HINT",
                hint_level=1,
                tutor_message="Yes, b can vary. What stays fixed?",
                tutor_message_voice_optimised="Yes, b can vary. What stays fixed?",
                reasoning_complete=False,
                confidence=0.96,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _PartialOpenAIClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question="What changes and what stays fixed?",
            correct_answer="b can vary; 3 stays fixed",
            answer_spec=_answer_spec(
                "b can vary; 3 stays fixed",
                ["b can vary", "3 stays fixed"],
                "CONCEPT_TEXT_MATCH",
            ),
            student_input="b can vary",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "PARTIALLY_CORRECT"
    assert response.question_completed is False


def test_guided_rubric_uses_only_the_compact_specialized_prompt(
    monkeypatch,
) -> None:
    request_bodies: list[dict[str, object]] = []

    class _GuidedHTTPClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "_GuidedHTTPClient":
            return self

        def __exit__(self, *exc) -> bool:
            return False

        def post(self, *args, **kwargs) -> _FakeOpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _FakeOpenAIResponse(
                json.dumps(
                    {
                        "question_id": "Q-T02-002",
                        "required_concepts": [
                            {
                                "concept_id": "PRODUCT_MEANING",
                                "description": "Explains adjacent-letter multiplication.",
                                "required": True,
                            }
                        ],
                        "completion_rule": "ALL_REQUIRED_CONCEPTS",
                        "cache_key": "model-value-is-replaced",
                        "prompt_version": "model-value-is-replaced",
                    }
                )
            )

    monkeypatch.setattr(openai_client.httpx, "Client", _GuidedHTTPClient)
    ai_client = openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=10,
        prompt_cache_key_enabled=False,
        store_responses=False,
        retry_count=0,
    )
    system_prompt = "Compact rubric prompt."
    ai_client.generate_guided_rubric(
        question_id="Q-T02-002",
        question_type="SHORT_RESPONSE",
        question="What does cd mean?",
        answer_spec=_answer_spec(
            "c × d",
            ["c times d"],
            "CONCEPT_TEXT_MATCH",
        ),
        potential_errors=[],
        target_micro_skill_ids=["T02.M2"],
        prompt_version="1.0.0",
        system_prompt=system_prompt,
    )

    assert len(request_bodies) == 1
    messages = request_bodies[0]["input"]
    assert isinstance(messages, list)
    assert messages == [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": messages[1]["content"],
        },
    ]
    assert "You are Numera" not in str(messages)


def test_guided_learning_supports_every_authored_answer_verification_method() -> None:
    rules = classifier.load_classifier_rules()

    assert set(rules.guided_learning.supported_verification_methods) == {
        "EXACT_CHOICE_MATCH",
        "EXACT_NOTATION_MATCH",
        "SYMBOLIC_EQUIVALENCE",
        "CONCEPT_TEXT_MATCH",
        "STRUCTURED_TEXT_MATCH",
        "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
        "CHOICE_AND_CONCEPT_MATCH",
        "BOOLEAN_AND_CONCEPT_MATCH",
    }


def test_guided_learning_rejects_an_unknown_verification_contract(
    monkeypatch,
) -> None:
    class _UnusedGuidedClient:
        pass

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _UnusedGuidedClient(),
    )

    with pytest.raises(
        AdapterError,
        match="Unsupported Guided Learning verification method",
    ):
        classify_student_response(
            ClassificationRequest(
                question_id="Q-UNKNOWN",
                question="Explain this.",
                correct_answer="An answer.",
                answer_spec=_answer_spec(
                    "An answer.",
                    [],
                    "UNKNOWN_FUTURE_METHOD",
                ),
                phase_2_prompt_context=_guided_context(0),
                student_input="A response.",
                current_phase="GUIDED_PRACTICE",
                input_source="TEXT",
                transcript_confidence=None,
                attempt_count=1,
                current_hint_level=None,
            )
        )


@pytest.mark.parametrize(
    ("student_input", "original_answer_correct"),
    [
        ("y", False),
        ("y is repeated four times, so the answer is 4y", True),
    ],
)
def test_scaffold_semantic_evaluator_accepts_the_requested_fact_or_full_answer(
    monkeypatch,
    student_input: str,
    original_answer_correct: bool,
) -> None:
    class _ScaffoldClient:
        def evaluate_scaffold_step(self, **kwargs):
            return ScaffoldStepEvaluation(
                step_satisfied=True,
                original_answer_correct=original_answer_correct,
                demonstrated_fact="The repeated term is y.",
                confidence=0.97,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ScaffoldClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-001",
            question="Which term or factor is repeated?",
            correct_answer="Identify the repeated letter or base",
            answer_spec=None,
            phase_2_prompt_context=_guided_context(0),
            scaffold_evaluation_context=ScaffoldEvaluationContext(
                scaffold_id="SCF-T02-WRITE-COMPACT",
                step_id="SCF-T02-WR-S1",
                original_question=(
                    "Write y + y + y + y in compact algebraic notation."
                ),
                canonical_answer="4y",
                accepted_answers=["4y", "4 × y"],
                verification_method="EXACT_NOTATION_MATCH",
                step_prompt="Which term or factor is repeated?",
                expected_response_criterion="Identify the repeated letter or base",
                completed_step_ids=[],
            ),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=2,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.scaffold_original_answer_correct is original_answer_correct


def test_scaffold_semantic_evaluator_rejects_an_unrelated_response(
    monkeypatch,
) -> None:
    class _ScaffoldClient:
        def evaluate_scaffold_step(self, **kwargs):
            return ScaffoldStepEvaluation(
                step_satisfied=False,
                original_answer_correct=False,
                demonstrated_fact=None,
                confidence=0.96,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ScaffoldClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-001",
            question="Which term or factor is repeated?",
            correct_answer="Identify the repeated letter or base",
            answer_spec=None,
            phase_2_prompt_context=_guided_context(0),
            scaffold_evaluation_context=ScaffoldEvaluationContext(
                scaffold_id="SCF-T02-WRITE-COMPACT",
                step_id="SCF-T02-WR-S1",
                original_question=(
                    "Write y + y + y + y in compact algebraic notation."
                ),
                canonical_answer="4y",
                accepted_answers=["4y", "4 × y"],
                verification_method="EXACT_NOTATION_MATCH",
                step_prompt="Which term or factor is repeated?",
                expected_response_criterion="Identify the repeated letter or base",
                completed_step_ids=[],
            ),
            student_input="the operation is subtraction",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=2,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "INCORRECT"
    assert response.scaffold_original_answer_correct is False
