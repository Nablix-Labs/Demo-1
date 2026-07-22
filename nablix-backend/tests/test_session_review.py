from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from app.ai_engine import session_review
from app.core.config import get_settings
from app.main import app
from app.models.session_review import GeneratedSessionReview, SessionReviewRequest


client = TestClient(app)


def _request_body() -> dict[str, object]:
    return {
        "session_summary": {
            "session_id": "SESSION001",
            "student_id": "ST001",
            "concept_id": "ALG_LINEAR_ONE_STEP",
            "session_date": "2026-07-10T10:00:00Z",
            "session_duration_seconds": 1240,
            "interaction_mode": "VOICE",
            "phase_4_entry_reason": "normal_review",
            "phases_completed": ["DIAGNOSTIC", "GUIDED_PRACTICE"],
            "session_performance": {
                "total_attempts": 3,
                "correct_attempts": 1,
                "incorrect_attempts": 2,
                "hints_used": 1,
                "hint_levels_used": [1],
                "canvas_submissions": 1,
                "rescue_mode_activations": 0,
                "long_pressure_events": 0,
                "voice_fallback_events": 0,
            },
            "per_question_history": [
                {
                    "question_id": "ALG_EQ_DIAG_001",
                    "phase": "GUIDED_PRACTICE",
                    "attempt_number": 1,
                    "evaluation": "INCORRECT",
                    "error_type": "ARITHMETIC_ERROR",
                    "hint_level_used": 1,
                    "independent_success": False,
                    "canvas_submitted": True,
                    "canvas_first_error_step": 3,
                    "canvas_first_error_type": "ARITHMETIC_ERROR",
                    "successful_step_descriptions": ["Selected the inverse operation correctly"],
                    "error_description": "The final calculation was incorrect",
                    "rescue_activated": False,
                },
                {
                    "question_id": "ALG_EQ_DIAG_001",
                    "phase": "GUIDED_PRACTICE",
                    "attempt_number": 2,
                    "evaluation": "INCORRECT",
                    "error_type": "ARITHMETIC_ERROR",
                    "hint_level_used": None,
                    "independent_success": False,
                    "canvas_submitted": False,
                    "canvas_first_error_step": None,
                    "canvas_first_error_type": None,
                    "successful_step_descriptions": [],
                    "error_description": "The calculation still needed checking",
                    "rescue_activated": False,
                },
                {
                    "question_id": "ALG_EQ_DIAG_001",
                    "phase": "GUIDED_PRACTICE",
                    "attempt_number": 3,
                    "evaluation": "CORRECT",
                    "error_type": None,
                    "hint_level_used": None,
                    "independent_success": True,
                    "canvas_submitted": False,
                    "canvas_first_error_step": None,
                    "canvas_first_error_type": None,
                    "successful_step_descriptions": ["Checked the final calculation independently"],
                    "error_description": None,
                    "rescue_activated": False,
                },
            ],
            "canvas_feedback_history": [
                {
                    "canvas_snapshot_id": "CANVAS001",
                    "question_id": "ALG_EQ_DIAG_001",
                    "overall_evaluation": "PARTIALLY_CORRECT",
                    "first_error_step": 3,
                    "first_error_type": "ARITHMETIC_ERROR",
                }
            ],
            "phase_transitions": [],
        },
        "student_model": {
            "mastery_status": "DEVELOPING",
            "error_counts": {"ARITHMETIC_ERROR": 2},
            "dominant_error_type": "ARITHMETIC_ERROR",
            "hint_dependency_score": 0.4,
            "error_confirmed_pattern": False,
            "recommended_entry_phase": "GUIDED_PRACTICE",
            "next_concept_recommendation": None,
        },
    }


def _validated_request(body: dict[str, object]) -> SessionReviewRequest:
    return SessionReviewRequest.model_validate_json(json.dumps(body))


@pytest.fixture(autouse=True)
def disable_openai(monkeypatch):
    monkeypatch.setenv("NABLIX_USE_OPENAI_AI_ENGINE", "false")
    monkeypatch.delenv("NABLIX_OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_valid_session_review_returns_complete_contract() -> None:
    response = client.post("/session/review/generate", json=_request_body())

    assert response.status_code == 200
    body = response.json()
    assert body["call_to_action"] == "CONTINUE_PRACTICE"
    assert body["answer_reveal_allowed"] is False
    assert body["guardrail_passed"] is True
    assert body["five_category_summary"]["category_3_pattern"] is None


def test_non_normal_review_is_rejected() -> None:
    body = _request_body()
    body["session_summary"]["phase_4_entry_reason"] = "close_out"

    response = client.post("/session/review/generate", json=body)

    assert response.status_code == 422


def test_empty_history_is_rejected() -> None:
    body = _request_body()
    body["session_summary"]["per_question_history"] = []

    response = client.post("/session/review/generate", json=body)

    assert response.status_code == 422


def test_question_attempts_must_be_chronological() -> None:
    body = _request_body()
    body["session_summary"]["per_question_history"][1]["attempt_number"] = 1

    response = client.post("/session/review/generate", json=body)

    assert response.status_code == 422


def test_unregistered_question_is_rejected() -> None:
    body = _request_body()
    body["session_summary"]["per_question_history"][0]["question_id"] = "UNKNOWN"

    response = client.post("/session/review/generate", json=body)

    assert response.status_code == 422


def test_openai_context_excludes_private_and_answer_fields() -> None:
    request = _validated_request(_request_body())
    config = session_review.load_session_review_config()
    evidence = session_review.build_review_evidence(request, config)

    context = session_review.build_openai_review_context(evidence, config)

    serialized = str(context)
    assert "SESSION001" not in serialized
    assert "ST001" not in serialized
    assert "CANVAS001" not in serialized
    assert "x = 5" not in serialized
    assert "question_id" not in serialized


def test_guardrail_failure_retries_once_then_uses_fallback(monkeypatch) -> None:
    generated = GeneratedSessionReview(
        five_category_summary={
            "category_1_strength": "The answer is x = 5.",
            "category_2_first_error": None,
            "category_3_pattern": None,
            "category_4_next_practice": "Check the calculation.",
            "category_5_mastery": "The skill is developing.",
        },
        student_facing_summary="The answer is x = 5.",
        b6_hook="Check one step next time.",
    )

    class _RevealingClient:
        generation_calls: int = 0
        retry_calls: int = 0

        def generate_session_review(
            self,
            context: dict[str, object],
            schema: dict[str, object],
        ) -> dict[str, object]:
            self.generation_calls += 1
            return generated.model_dump()

        def regenerate_session_review(
            self,
            context: dict[str, object],
            schema: dict[str, object],
            stricter_instruction: str,
        ) -> dict[str, object]:
            self.retry_calls += 1
            return generated.model_dump()

    fake_client = _RevealingClient()
    monkeypatch.setattr(
        session_review,
        "build_openai_session_review_client",
        lambda settings: fake_client,
    )
    request = _validated_request(_request_body())

    response = session_review.generate_session_review(request)

    assert fake_client.generation_calls == 1
    assert fake_client.retry_calls == 1
    assert response.guardrail_passed is True
    assert "x = 5" not in str(response.model_dump())


def test_mastered_and_pressure_actions_are_deterministic() -> None:
    mastered_body = _request_body()
    mastered_body["student_model"]["mastery_status"] = "MASTERED"
    mastered_request = _validated_request(mastered_body)
    assert session_review.select_call_to_action(mastered_request) == "NEXT_TOPIC"

    pressure_body = _request_body()
    pressure_body["session_summary"]["session_performance"]["long_pressure_events"] = 1
    pressure_request = _validated_request(pressure_body)
    assert session_review.select_call_to_action(pressure_request) == "NONE"


def test_error_free_review_removes_error_categories() -> None:
    body = _request_body()
    body["session_summary"]["session_performance"]["correct_attempts"] = 3
    body["session_summary"]["session_performance"]["incorrect_attempts"] = 0
    for attempt in body["session_summary"]["per_question_history"]:
        attempt["evaluation"] = "CORRECT"
        attempt["error_type"] = None
        attempt["error_description"] = None
    body["student_model"]["error_counts"] = {}
    body["student_model"]["dominant_error_type"] = None
    request = _validated_request(body)
    generated = session_review.build_fallback_review(
        session_review.build_review_evidence(
            request,
            session_review.load_session_review_config(),
        ),
        session_review.load_session_review_config(),
    )

    result = session_review.apply_deterministic_review_rules(
        generated,
        request,
        session_review.load_session_review_config(),
    )

    assert result.five_category_summary.category_2_first_error is None
    assert result.five_category_summary.category_3_pattern is None


def test_three_unconfirmed_errors_use_possible_pattern_wording() -> None:
    body = _request_body()
    body["student_model"]["error_counts"] = {"ARITHMETIC_ERROR": 3}
    request = _validated_request(body)
    config = session_review.load_session_review_config()
    generated = session_review.build_fallback_review(
        session_review.build_review_evidence(request, config),
        config,
    )

    result = session_review.apply_deterministic_review_rules(generated, request, config)

    assert result.five_category_summary.category_3_pattern is not None
    assert "possible" in result.five_category_summary.category_3_pattern.lower()


def test_tamil_confirmed_pattern_uses_factual_wording() -> None:
    body = _request_body()
    body["student_model"]["error_confirmed_pattern"] = True
    request = _validated_request(body)
    config = session_review.load_session_review_config()
    generated = session_review.build_fallback_review(
        session_review.build_review_evidence(request, config),
        config,
    )

    result = session_review.apply_deterministic_review_rules(generated, request, config)

    assert result.five_category_summary.category_3_pattern is not None
    assert "possible" not in result.five_category_summary.category_3_pattern.lower()


def test_pressure_suppresses_b6_hook() -> None:
    body = _request_body()
    body["session_summary"]["session_performance"]["long_pressure_events"] = 1
    request = _validated_request(body)
    config = session_review.load_session_review_config()
    generated = session_review.build_fallback_review(
        session_review.build_review_evidence(request, config),
        config,
    )

    result = session_review.apply_deterministic_review_rules(generated, request, config)

    assert result.b6_hook is None
