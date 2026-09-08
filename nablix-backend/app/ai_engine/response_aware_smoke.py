"""Opt-in synthetic replay: python -m app.ai_engine.response_aware_smoke.

Uses the configured Guided model and NABLIX_OPENAI_API_KEY. No student records
are written. Checks classification, evidence, accounting and bounded wording
regressions; printed replies still require qualitative review. Conversation
cases carry the real returned objective, evidence and tutor history forward.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai_engine.classifier import (
    ClassificationRequest, build_openai_ai_engine_client,
    check_student_message_safety, classify_guided_learning_response,
    classify_scaffold_response, detect_student_intent,
)
from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.schemas import InputSource, TutorResponse
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.models.adapters import ConversationMessage, Phase2PromptContext
from app.models.guided_learning import (
    ActiveTeachingObjective, GeneratedConcept, GeneratedQuestionRubric,
    GuidedTeachingState, ScaffoldEvaluationContext,
)
from app.models.student_model_session import AnswerSpec, QuestionType


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    question: str
    answer: str
    prior: str
    input: str
    source: InputSource
    kind: str | None
    assessment: str
    question_type: QuestionType = "SHORT_RESPONSE"
    explanation_required: bool = False
    conversation_id: str | None = None
    concepts: list[GeneratedConcept] = Field(default_factory=lambda: [
        GeneratedConcept(concept_id="GENERAL_RULE", description="States the correct general rule.", required=True),
    ])
    expected_confirmed: list[str] = Field(default_factory=list)
    explanation_expected: bool = False
    forbidden_content: list[str] = Field(default_factory=list)
    scaffold: ScaffoldEvaluationContext | None = None


class ReplaySuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forbidden_reply: list[str]
    cases: list[ReplayCase]


@dataclass(frozen=True)
class ReplayHistory:
    messages: list[ConversationMessage]
    objective: ActiveTeachingObjective | None
    teaching: GuidedTeachingState | None


def replay_failures(case: ReplayCase, result: TutorResponse, forbidden_reply: list[str]) -> list[str]:
    """Test assertions only; never rewrite or select learner-facing wording."""
    failures: list[str] = []
    contribution = result.contribution
    if contribution is None:
        return ["missing contribution"]
    if contribution.assessment != case.assessment:
        failures.append("incorrect assessment")
    if case.kind is not None and contribution.kind != case.kind:
        failures.append("incorrect contribution kind")
    if case.assessment == "NOT_ASSESSED":
        if result.attempt_increment or result.question_completed:
            failures.append("non-attempt graded or completed")
        if contribution.support_relevance != "NOT_NEEDED":
            failures.append("support on non-attempt")
    if case.assessment == "INCORRECT" and result.question_completed:
        failures.append("incorrect answer completed question")
    if case.explanation_expected and not contribution.explained_idea:
        failures.append("requested explanation not recorded")
    confirmed = set(result.guided_teaching_state.confirmed_component_ids) if result.guided_teaching_state else set()
    if not set(case.expected_confirmed).issubset(confirmed):
        failures.append("valid evidence lost")
    reply = result.tutor_message
    if reply.count("?") > 1:
        failures.append("multiple questions")
    for pattern in forbidden_reply:
        if re.search(pattern, reply, re.IGNORECASE):
            failures.append(f"wording regression: {pattern}")
    learner_content = "\n".join([
        reply, result.tutor_message_voice_optimised, contribution.generated_support_text or "",
        *[f"{row.expression} {row.annotation}" for row in contribution.generated_visual_rows or []],
    ])
    for pattern in case.forbidden_content:
        if re.search(pattern, learner_content, re.IGNORECASE):
            failures.append(f"content regression: {pattern}")
    return failures


def main() -> None:
    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={
            "response_aware_enabled": True,
            "production_boundary_enabled": True,
        },
    )})
    settings = get_settings().model_copy(update={
        "use_openai_ai_engine": True, "openai_ai_engine_model": rules.guided_learning.model,
    })
    if not settings.openai_api_key:
        raise RuntimeError("Configure NABLIX_OPENAI_API_KEY before running this live replay.")
    client = build_openai_ai_engine_client(settings)
    if client is None:
        raise RuntimeError("The configured Guided OpenAI client is unavailable.")
    path = Path(__file__).resolve().parents[2] / "configs" / "response_aware_eval.yaml"
    suite = ReplaySuite.model_validate(yaml.safe_load(path.read_text()))
    histories: dict[str, ReplayHistory] = {}
    failed_cases = 0
    for case in suite.cases:
        question_id = case.conversation_id or case.id
        previous = histories.get(question_id)
        history = previous.messages if previous else [ConversationMessage(role="assistant", content=case.prior)]
        request = ClassificationRequest(
            question_id=question_id, question_type=case.question_type, question=case.question,
            correct_answer=case.answer, student_input=case.input,
            answer_spec=AnswerSpec(answer_spec_id=question_id, canonical_answer=case.answer,
                                  accepted_answers=[], verification_method="STRUCTURED_TEXT_MATCH",
                                  explanation_required=case.explanation_required),
            phase_2_prompt_context=Phase2PromptContext(
                target_micro_skill_ids=[], support_state={}, potential_errors=[], support_catalog={},
                current_support=None, current_scaffold_step_number=0, consecutive_stuck_count=0,
            ),
            generated_question_rubric=GeneratedQuestionRubric(
                question_id=question_id, required_concepts=case.concepts,
                completion_rule="ALL_REQUIRED_CONCEPTS", cache_key=question_id, prompt_version="live-replay-2",
            ),
            current_phase="GUIDED_PRACTICE", input_source=case.source,
            transcript_confidence=0.95 if case.source == "VOICE" else None,
            attempt_count=0, current_hint_level=None, conversation_history=history,
            active_teaching_objective=previous.objective if previous else None,
            guided_teaching_state=previous.teaching if previous else None,
            scaffold_evaluation_context=case.scaffold,
        )
        start = monotonic()
        try:
            safety = check_student_message_safety(case.input, rules)
            if not safety.passed:
                raise AdapterError("live_replay", "Synthetic case unexpectedly failed the safety boundary.")
            intent = detect_student_intent(case.input, rules)
            if case.scaffold is not None:
                result = classify_scaffold_response(request, rules, safety, client, intent)
            else:
                result = classify_guided_learning_response(request, rules, safety, client, intent)
            failures = replay_failures(case, result, suite.forbidden_reply)
            failed_cases += int(bool(failures))
            histories[question_id] = ReplayHistory(
                messages=[*history, ConversationMessage(role="user", content=case.input),
                          ConversationMessage(role="assistant", content=result.tutor_message)],
                objective=result.active_teaching_objective, teaching=result.guided_teaching_state,
            )
            print(json.dumps({"case": case.id, "passed": not failures, "failures": failures,
                              "contribution": result.contribution.model_dump() if result.contribution else None,
                              "reply": result.tutor_message, "state": result.guided_student_state,
                              "completed": result.question_completed,
                              "confirmed": result.guided_teaching_state.confirmed_component_ids if result.guided_teaching_state else [],
                              "latency_ms": round((monotonic() - start) * 1000)}), flush=True)
        except (AdapterError, ValidationError, ValueError) as error:
            failed_cases += 1
            print(json.dumps({"case": case.id, "passed": False, "error": str(error)}), flush=True)
    print(json.dumps({"total": len(suite.cases), "failed": failed_cases,
                      "qualitative_review_required": True}), flush=True)
    if failed_cases:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
