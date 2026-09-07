"""Opt-in live interpretation replay: python -m app.ai_engine.response_aware_smoke.

Uses the configured API key and Guided model. It never writes a student journey
or changes the rollout flag. Printed responses are synthetic evaluation data.
"""
import json
from pathlib import Path
from time import monotonic

import yaml

from app.ai_engine.classifier import ClassificationRequest, build_openai_ai_engine_client, classify_guided_learning_response
from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.schemas import SafetyCheck
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.models.adapters import ConversationMessage, Phase2PromptContext
from app.models.guided_learning import GeneratedConcept, GeneratedQuestionRubric
from app.models.student_model_session import AnswerSpec


def main() -> None:
    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True},
    )})
    settings = get_settings().model_copy(update={
        "use_openai_ai_engine": True, "openai_ai_engine_model": rules.guided_learning.model,
    })
    if not settings.openai_api_key:
        raise RuntimeError("Load OPENAI_API_KEY from the backend environment before running this live replay.")
    client = build_openai_ai_engine_client(settings)
    if client is None:
        raise RuntimeError("The configured Guided OpenAI client is unavailable.")
    path = Path(__file__).resolve().parents[2] / "configs" / "response_aware_eval.yaml"
    cases = yaml.safe_load(path.read_text())["cases"]
    failures = 0
    for case in cases:
        request = ClassificationRequest(
            question_id=case["id"], question_type="SHORT_RESPONSE", question=case["question"],
            correct_answer=case["answer"], student_input=case["input"],
            answer_spec=AnswerSpec(answer_spec_id=case["id"], canonical_answer=case["answer"],
                                   accepted_answers=[], verification_method="STRUCTURED_TEXT_MATCH",
                                   explanation_required=False),
            phase_2_prompt_context=Phase2PromptContext(
                target_micro_skill_ids=[], support_state={}, potential_errors=[], support_catalog={},
                current_support=None, current_scaffold_step_number=0, consecutive_stuck_count=0,
            ),
            generated_question_rubric=GeneratedQuestionRubric(
                question_id=case["id"], required_concepts=[
                    GeneratedConcept(concept_id="GENERAL_RULE", description="States the correct general rule.", required=True),
                ], completion_rule="ALL_REQUIRED_CONCEPTS", cache_key=case["id"], prompt_version="live-replay-1",
            ),
            current_phase="GUIDED_PRACTICE", input_source=case["source"],
            transcript_confidence=0.95 if case["source"] == "VOICE" else None,
            attempt_count=0, current_hint_level=None,
            conversation_history=[ConversationMessage(role="assistant", content=case["prior"])],
        )
        start = monotonic()
        try:
            result = classify_guided_learning_response(
                request, rules, SafetyCheck(passed=True, flag_type=None, action_taken=None), client, "SUBMITTING_ANSWER",
            )
            contribution = result.contribution
            passed = contribution is not None and contribution.assessment == case["assessment"]
            if case["kind"] is not None:
                passed = passed and contribution is not None and contribution.kind == case["kind"]
            failures += int(not passed)
            print(json.dumps({"case": case["id"], "passed": passed,
                              "contribution": contribution.model_dump() if contribution else None,
                              "reply": result.tutor_message, "latency_ms": round((monotonic() - start) * 1000)}))
        except AdapterError as error:
            failures += 1
            print(json.dumps({"case": case["id"], "passed": False, "error": str(error)}))
    print(json.dumps({"total": len(cases), "failed": failures}))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
