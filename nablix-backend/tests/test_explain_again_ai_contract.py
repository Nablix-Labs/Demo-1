import json

import pytest

from app.ai_engine import openai_client
from app.ai_engine.prompt_registry import load_prompt_registry
from app.ai_engine.schemas import (
    ExplainAgainConversationMessage,
    ExplainAgainRequest,
    ExplainAgainSupportState,
    ExplainAgainVisualCue,
    OpenAIExplainAgainMessage,
)
from app.core.exceptions import AdapterError
from app.models.guided_learning import (
    ActiveScaffold,
    ActiveTeachingObjective,
    GeneratedConcept,
    GeneratedQuestionRubric,
)


class _OpenAIResponse:
    status_code = 200

    def __init__(self, content: str) -> None:
        self.text = content
        self._content = content

    def json(self) -> dict[str, str]:
        return {"output_text": self._content}


def _request() -> ExplainAgainRequest:
    return ExplainAgainRequest(
        question="What does cd mean?",
        generated_question_rubric=GeneratedQuestionRubric(
            question_id="Q-T02-002",
            required_concepts=[
                GeneratedConcept(
                    concept_id="PRODUCT_MEANING",
                    description="Adjacent letters represent multiplication.",
                    required=True,
                )
            ],
            completion_rule="ALL_REQUIRED_CONCEPTS",
            cache_key="rubric-key",
            prompt_version="1.0.0",
        ),
        active_teaching_objective=ActiveTeachingObjective(
            objective_type="ANSWER_QUESTION",
            target_concept_ids=["PRODUCT_MEANING"],
            confirmed_concept_ids=[],
            missing_concept_ids=["PRODUCT_MEANING"],
        ),
        first_unresolved_concept_id="PRODUCT_MEANING",
        recent_conversation=[
            ExplainAgainConversationMessage(
                role="assistant",
                content="Think about multiplication.",
            )
        ],
        visible_cue=ExplainAgainVisualCue(
            show=True,
            cue_type="EQUATION_BLOCK",
            description="c × d",
            actions=[],
        ),
        active_scaffold=ActiveScaffold(
            scaffold_id="S-1",
            current_step_id="S-1-STEP-1",
            step_number=1,
            total_steps=2,
            step_text="Name the operation.",
            step_voice="Name the operation.",
        ),
        support_state=ExplainAgainSupportState(
            active_support_level="SCAFFOLD",
            highest_support_used="SCAFFOLD",
            support_reason_code="REPEATED_WRONG",
        ),
        selected_error_code="MULTIPLICATION_NOTATION",
        misconception_evidence="The learner read cd as addition.",
    )


def _client() -> openai_client.OpenAIAIEngineClient:
    return openai_client.OpenAIAIEngineClient(
        api_key="sk-test",
        model="gpt-test",
        timeout_seconds=10,
        prompt_cache_key_enabled=False,
        store_responses=False,
        retry_count=0,
        guided_reasoning_effort="low",
        guided_model_supports_reasoning_effort=False,
        guided_verbosity="low",
    )


def test_generate_explain_again_uses_strict_state_preserving_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_bodies: list[dict[str, object]] = []

    class _HTTPClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_HTTPClient":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, *args: object, **kwargs: object) -> _OpenAIResponse:
            request_bodies.append(kwargs["json"])
            return _OpenAIResponse(
                json.dumps(
                    {
                        "tutor_message": "Here is another way to think about it.",
                        "tutor_message_voice": "Here is another way to think about it.",
                        "answer_reveal_allowed": False,
                        "progression_change_requested": False,
                        "attempt_increment": 0,
                    }
                )
            )

    monkeypatch.setattr(openai_client.httpx, "Client", _HTTPClient)

    response = _client().generate_explain_again_response(
        _request(),
        "Rephrase the active objective without changing pedagogical state.",
    )

    assert response.attempt_increment == 0
    assert response.progression_change_requested is False
    user_messages = [
        message
        for message in request_bodies[0]["input"]
        if message["role"] == "user"
    ]
    assert {
        "role": "assistant",
        "content": "Think about multiplication.",
    } in request_bodies[0]["input"]
    registry = load_prompt_registry()
    messages = request_bodies[0]["input"]
    assert messages[0] == {"role": "system", "content": registry.layer_1_core}
    assert messages[1]["role"] == "system"
    assert "PHASE 2" in messages[1]["content"]
    assert messages[2] == {
        "role": "system",
        "content": "Rephrase the active objective without changing pedagogical state.",
    }
    user_payload = json.loads(user_messages[-1]["content"])
    assert user_payload["component"] == "explain_again_response"
    assert user_payload["first_unresolved_concept_id"] == "PRODUCT_MEANING"
    assert user_payload["active_scaffold"]["current_step_id"] == "S-1-STEP-1"
    assert user_payload["support_state"]["active_support_level"] == "SCAFFOLD"


def test_explain_again_message_schema_requires_answer_reveal_risk() -> None:
    schema = OpenAIExplainAgainMessage.model_json_schema()

    assert "answer_reveal_risk" in schema["required"]


def test_generate_explain_again_rejects_state_changing_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _HTTPClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_HTTPClient":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, *args: object, **kwargs: object) -> _OpenAIResponse:
            return _OpenAIResponse(
                json.dumps(
                    {
                        "tutor_message": "Advance to the next question.",
                        "tutor_message_voice": "Advance to the next question.",
                        "answer_reveal_allowed": False,
                        "progression_change_requested": True,
                        "attempt_increment": 1,
                    }
                )
            )

    monkeypatch.setattr(openai_client.httpx, "Client", _HTTPClient)

    with pytest.raises(AdapterError, match="invalid Explain Again response"):
        _client().generate_explain_again_response(_request(), "Rephrase only.")
