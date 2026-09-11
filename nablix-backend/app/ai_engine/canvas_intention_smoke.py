"""Live check for a confirmed concept becoming a valid canvas action.

Run with ``python -m app.ai_engine.canvas_intention_smoke`` after loading only
``NABLIX_OPENAI_API_KEY``. It creates no student records.
"""
import json
from pathlib import Path

import yaml

from app.ai_engine.classifier import (
    ClassificationRequest,
    build_openai_ai_engine_client,
    check_student_message_safety,
    classify_guided_learning_response,
    detect_student_intent,
)
from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.response_aware_smoke import ReplaySuite
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.models.adapters import ConversationMessage, Phase2PromptContext
from app.models.guided_learning import GeneratedQuestionRubric
from app.models.student_model_session import AnswerSpec
from app.services.canvas_annotations import plan_tutor_canvas_actions
from app.services.question_anchors import plan_canvas_action_anchors


def live_canvas_intention_check() -> None:
    """Verify that confirmed evidence produces a grounded tutor action."""

    rules = load_classifier_rules()
    enabled_rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True, "production_boundary_enabled": True},
    )})
    settings = get_settings().model_copy(update={
        "use_openai_ai_engine": True,
        "openai_ai_engine_model": enabled_rules.guided_learning.model,
    })
    if not settings.openai_api_key:
        raise RuntimeError("Configure NABLIX_OPENAI_API_KEY before running this check.")
    client = build_openai_ai_engine_client(settings)
    if client is None:
        raise RuntimeError("The configured Guided OpenAI client is unavailable.")

    suite_path = Path(__file__).resolve().parents[2] / "configs" / "response_aware_eval.yaml"
    suite = ReplaySuite.model_validate(yaml.safe_load(suite_path.read_text()))
    case = next(item for item in suite.cases if item.id == "correct_expression")
    request = ClassificationRequest(
        question_id=case.id,
        question_type=case.question_type,
        question=case.question,
        correct_answer=case.answer,
        student_input=case.input,
        answer_spec=AnswerSpec(
            answer_spec_id=case.id,
            canonical_answer=case.answer,
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=case.explanation_required,
        ),
        phase_2_prompt_context=Phase2PromptContext(
            target_micro_skill_ids=[], support_state={}, potential_errors=[], support_catalog={},
            current_support=None, current_scaffold_step_number=0, consecutive_stuck_count=0,
        ),
        generated_question_rubric=GeneratedQuestionRubric(
            question_id=case.id,
            required_concepts=case.concepts,
            completion_rule="ALL_REQUIRED_CONCEPTS",
            cache_key=case.id,
            prompt_version="live-canvas-intention-check",
        ),
        current_phase="GUIDED_PRACTICE",
        input_source=case.source,
        transcript_confidence=None,
        canvas_solution_complete_candidate=True,
        attempt_count=0,
        current_hint_level=None,
        conversation_history=[ConversationMessage(role="assistant", content=case.prior)],
        active_teaching_objective=None,
        guided_teaching_state=None,
        scaffold_evaluation_context=None,
    )
    safety = check_student_message_safety(case.input, enabled_rules)
    if not safety.passed:
        raise AdapterError("live_canvas_intention", "The synthetic student input failed safety checks.")
    tutor = classify_guided_learning_response(
        request,
        enabled_rules,
        safety,
        client,
        detect_student_intent(case.input, enabled_rules),
    )
    anchors = plan_canvas_action_anchors(case.id, case.question)
    actions = plan_tutor_canvas_actions(
        tutor=tutor,
        question_anchors=anchors,
        canvas_events=[],
        turn_id="LIVE-CANVAS-001",
        canonical_answer=case.answer,
        fallback_labels=enabled_rules.guided_learning.fallback_canvas_labels,
        wrong_attempt_count=0,
        student_response=case.input,
    )
    payload = {
        "reply": tutor.tutor_message,
        "confirmed_components": (
            tutor.guided_teaching_state.confirmed_component_ids
            if tutor.guided_teaching_state is not None else []
        ),
        "validated_actions": [action.model_dump() for action in actions],
    }
    print(json.dumps(payload, indent=2), flush=True)
    if not actions:
        raise SystemExit("FAIL: confirmed evidence produced no canvas action.")


if __name__ == "__main__":
    live_canvas_intention_check()
