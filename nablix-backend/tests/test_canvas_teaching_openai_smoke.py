import os

import pytest

from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.openai_client import OpenAIAIEngineClient
from app.core.config import Settings


def test_openai_canvas_teaching_plan_smoke() -> None:
    """Runs only when a VM explicitly opts into a billed OpenAI smoke test."""

    if os.getenv("NABLIX_RUN_OPENAI_SMOKE") != "true":
        pytest.skip("Set NABLIX_RUN_OPENAI_SMOKE=true to run the billed OpenAI smoke test.")

    settings = Settings(use_openai_ai_engine=True)
    if settings.openai_api_key == "":
        pytest.skip("Set NABLIX_OPENAI_API_KEY to run the OpenAI smoke test.")

    rules = load_classifier_rules()
    client = OpenAIAIEngineClient(
        api_key=settings.openai_api_key,
        model=rules.guided_learning.model,
        timeout_seconds=settings.openai_request_timeout_seconds,
        prompt_cache_key_enabled=settings.openai_prompt_cache_key_enabled,
        store_responses=settings.openai_store_responses,
        retry_count=settings.adapter_request_retry_count,
        guided_reasoning_effort=rules.guided_learning.reasoning_effort,
        guided_model_supports_reasoning_effort=(
            rules.guided_learning.model_supports_reasoning_effort
        ),
        guided_verbosity=rules.guided_learning.verbosity,
    )

    narration = "Look at the first numbers. What do you notice about them?"
    plan = client.plan_canvas_teaching(
        system_prompt=rules.guided_learning.canvas_teaching.system_prompt,
        context={
            "question_id": "SMOKE-PATTERN-1",
            "question": "3 + 5 | 9 + 5 | 14 + 5. Use n for the changing starting number.",
            "tutor_message_voice": narration,
            "student_response": "I do not know.",
            "allowed_target_ids": [
                "SMOKE-PATTERN-1:QTOKEN:1",
                "ZONE:QUESTION",
                "ZONE:REASONING",
                "ZONE:TUTOR_SOLUTION",
            ],
            "current_turn_evidence_ids": [],
            "teaching_mode": "HINT",
            "active_support_level": "HINT",
            "current_unresolved_component_id": "FIXED_VALUE",
            "direct_explanation_authorized": False,
            "direct_explanation_evidence_ref": rules.guided_learning.canvas_teaching.direct_explanation_evidence_ref,
            "direct_explanation_maximum_written_operations": rules.guided_learning.canvas_teaching.direct_explanation_maximum_written_operations,
            "tutor_solved_active": False,
            "tutor_solved_answer_authorized": False,
            "tutor_solved_actions": [],
            "maximum_beats": rules.guided_learning.canvas_teaching.maximum_beats,
            "maximum_operations_per_beat": 4,
            "rules": {
                "write_only_confirmed_ideas": True,
                "support_pane_content_must_not_be_copied": True,
                "student_write_area_is_forbidden": True,
                "raw_coordinates_are_forbidden": True,
            },
        },
    )

    assert plan.beats
    for beat in plan.beats:
        anchor = beat.speech_anchor
        assert narration[anchor.start_char:anchor.end_char] == anchor.text
        for operation in beat.operations:
            assert operation.kind not in {"WRITE_TEXT", "WRITE_MATH"}
            assert set(operation.target_ids).issubset(
                {
                    "SMOKE-PATTERN-1:QTOKEN:1",
                    "ZONE:QUESTION",
                    "ZONE:REASONING",
                    "ZONE:TUTOR_SOLUTION",
                }
            )
