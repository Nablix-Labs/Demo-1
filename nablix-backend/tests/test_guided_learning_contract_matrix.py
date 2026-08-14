from dataclasses import dataclass
from typing import Literal

import pytest

from app.ai_engine import classifier
from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.core.config import Settings
from app.models.adapters import Phase2PromptContext
from app.models.guided_learning import (
    ActiveTeachingObjective,
    HybridCanvasPlannerRequest,
    HybridPedagogyDecision,
    HybridSemanticEvaluation,
    HybridTutorRequest,
    HybridTutorWordingRequest,
    HybridAuthoredSupportContent,
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedEvaluation,
)
from app.models.student_model_session import AnswerSpec


ExpectedState = Literal["CORRECT", "PARTIAL", "WRONG", "STUCK"]


@dataclass(frozen=True)
class AuthoredQuestion:
    question_id: str
    question: str
    canonical_answer: str
    accepted_answers: list[str]
    verification_method: str
    micro_skill_id: str
    error_code: str
    correct_response: str
    partial_response: str
    wrong_response: str


AUTHORED_GUIDED_QUESTIONS: list[AuthoredQuestion] = [
    AuthoredQuestion(
        question_id="Q-T02-001",
        question="Write y + y + y + y in compact algebraic notation.",
        canonical_answer="4y",
        accepted_answers=["4y", "4 × y"],
        verification_method="EXACT_NOTATION_MATCH",
        micro_skill_id="T02.M2",
        error_code="ERR-T02-COEFFICIENT-NOTATION",
        correct_response="4y",
        partial_response="y is repeated four times",
        wrong_response="4 + y",
    ),
    AuthoredQuestion(
        question_id="Q-T02-002",
        question="What operation is represented by cd? Explain briefly.",
        canonical_answer="c × d",
        accepted_answers=["c times d", "c multiplied by d", "product of c and d"],
        verification_method="CONCEPT_TEXT_MATCH",
        micro_skill_id="T02.M3",
        error_code="ERR-T02-ADJACENT-LETTERS-ADDITION",
        correct_response="c multiplied by d",
        partial_response="multiplication",
        wrong_response="c + d",
    ),
    AuthoredQuestion(
        question_id="Q-T02-003",
        question="Write p × p × q in compact algebraic notation.",
        canonical_answer="p²q",
        accepted_answers=["p²q", "p^2q"],
        verification_method="EXACT_NOTATION_MATCH",
        micro_skill_id="T02.M5",
        error_code="ERR-T02-POWER-AS-COEFFICIENT",
        correct_response="p^2q",
        partial_response="p is repeated twice",
        wrong_response="2pq",
    ),
    AuthoredQuestion(
        question_id="Q-T02-004",
        question=(
            "Which statement is correct? A) a² means 2a. "
            "B) a² means a × a. Explain briefly."
        ),
        canonical_answer="B",
        accepted_answers=["B", "a × a", "a multiplied by itself"],
        verification_method="CHOICE_AND_CONCEPT_MATCH",
        micro_skill_id="T02.M4",
        error_code="ERR-T02-POWER-AS-COEFFICIENT",
        correct_response="B because a squared means a times a",
        partial_response="B",
        wrong_response="A because it means 2a",
    ),
    AuthoredQuestion(
        question_id="Q-T02-005",
        question=(
            "Decode each expression without calculating or expanding: "
            "4n, pq, r², c/d and 2(x + 1)."
        ),
        canonical_answer="4 × n; p × q; r × r; c ÷ d; 2 × (x + 1)",
        accepted_answers=[
            "four times n",
            "p times q",
            "r squared means r times r",
            "c divided by d",
            "two times the whole bracket",
        ],
        verification_method="STRUCTURED_TEXT_MATCH",
        micro_skill_id="T02.M7",
        error_code="ERR-T02-BRACKET-GROUP-IGNORED",
        correct_response=(
            "four times n; p times q; r times r; c divided by d; "
            "two times the whole bracket x plus one"
        ),
        partial_response="4n means four times n",
        wrong_response="4+n, p+q, 2r, c-d, and 2x+1",
    ),
    AuthoredQuestion(
        question_id="Q-T02-010",
        question=(
            "Write ½ × x using compact algebraic notation with the "
            "fractional coefficient directly before the letter."
        ),
        canonical_answer="½x",
        accepted_answers=["½x", "(1/2)x"],
        verification_method="EXACT_NOTATION_MATCH",
        micro_skill_id="T02.M8",
        error_code="ERR-T02-FRACTIONAL-COEFFICIENT-MISREAD",
        correct_response="1/2x",
        partial_response="one half is the coefficient",
        wrong_response="one half plus x",
    ),
]


def _hybrid_topic_1_envelope() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "question_id": "Q-T01-003",
        "question_type": "SHORT_RESPONSE",
        "question": "A player starts with score s and gains 6 bonus points. Write the new-score rule.",
        "answer_spec": {
            "answer_spec_id": "ANS-T01-003",
            "canonical_answer": "s + 6",
            "accepted_answers": ["s+6"],
            "verification_method": "EXACT_NOTATION_MATCH",
            "answer_steps": ["Identify the changing score.", "Write the rule."],
        },
        "support_state": {
            "current_support": "NONE",
            "highest_support_used": "NONE",
            "active_support_id": None,
            "support_history_ids": [],
            "consecutive_stuck_count": 0,
        },
        "session_history": [],
        "ordered_canvas_memory": [
            {
                "object_id": "student-score-note",
                "order_index": 0,
                "turn_id": "TURN-003",
                "question_id": "Q-T01-003",
                "actor": "STUDENT",
                "action_type": "WRITE",
                "content": "score changes",
                "math_text": None,
                "target_object_id": None,
                "semantic_tag": "changing_value",
                "source_id": None,
                "active_state": "ACTIVE",
                "reliability": "RELIABLE",
            }
        ],
        "student_evidence": {
            "input_source": "MULTIMODAL",
            "raw_voice_transcript": "sex plus six",
            "transcript_confidence": 0.98,
            "transcript_alternatives": ["s plus six"],
            "typed_answer": None,
            "structured_answer": {},
            "selected_option_id": None,
            "selected_option_text": None,
            "raw_ocr_text": "s + 6",
            "processed_math_text": "s + 6",
            "ocr_confidence": 0.96,
            "canvas_object_ids": ["student-score-note"],
        },
        "pedagogical_state": {
            "student_state": "PARTIAL",
            "completed_component_ids": [],
            "current_answer_step_index": 0,
            "consecutive_stuck_count": 0,
        },
    }


def _hybrid_enabled_rules() -> classifier.ClassifierRulesConfig:
    rules = classifier.load_classifier_rules()
    guided_learning = rules.guided_learning.model_copy(
        update={
            "v1_hybrid_enabled": True,
            "canvas_pedagogy_action_planner_enabled": True,
        }
    )
    return rules.model_copy(update={"guided_learning": guided_learning})


def _rubric(question_id: str) -> GeneratedQuestionRubric:
    return GeneratedQuestionRubric(
        question_id=question_id,
        required_concepts=[
            GeneratedConcept(
                concept_id="PRIMARY_FACT",
                description="Identifies the main mathematical relationship.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="COMPLETE_RESPONSE",
                description="Gives every part required by the question.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key=f"rubric-{question_id}",
        prompt_version="1.0.0",
    )


def _evaluation(
    state: ExpectedState,
    objective: ActiveTeachingObjective,
    error_code: str,
) -> GuidedEvaluation:
    if state == "CORRECT":
        return GuidedEvaluation(
            student_state=state,
            newly_confirmed_concept_ids=["PRIMARY_FACT", "COMPLETE_RESPONSE"],
            preserved_concept_ids=[],
            contradicted_concept_ids=[],
            missing_concept_ids=[],
            selected_error_code=None,
            confidence=0.98,
            next_objective=None,
            tutor_message="That addresses the complete question.",
            tutor_message_voice="That addresses the complete question.",
        )
    if state == "PARTIAL":
        return GuidedEvaluation(
            student_state=state,
            newly_confirmed_concept_ids=["PRIMARY_FACT"],
            preserved_concept_ids=[],
            contradicted_concept_ids=[],
            missing_concept_ids=["COMPLETE_RESPONSE"],
            selected_error_code=None,
            confidence=0.96,
            next_objective=ActiveTeachingObjective(
                objective_type="COMPLETE_RESPONSE",
                target_concept_ids=["COMPLETE_RESPONSE"],
                confirmed_concept_ids=[],
                missing_concept_ids=["COMPLETE_RESPONSE"],
            ),
            tutor_message="That establishes one part. What is still missing?",
            tutor_message_voice="That establishes one part. What is still missing?",
        )
    if state == "WRONG":
        return GuidedEvaluation(
            student_state=state,
            newly_confirmed_concept_ids=[],
            preserved_concept_ids=[],
            contradicted_concept_ids=[],
            missing_concept_ids=objective.missing_concept_ids,
            selected_error_code=error_code,
            confidence=0.97,
            next_objective=objective,
            tutor_message="Test that idea against the relationship in the question.",
            tutor_message_voice="Test that idea against the relationship in the question.",
        )
    return GuidedEvaluation(
        student_state=state,
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=objective.missing_concept_ids,
        selected_error_code=None,
        confidence=0.95,
        next_objective=objective,
        tutor_message="Let’s make the question smaller and focus on one relationship.",
        tutor_message_voice="Let’s make the question smaller and focus on one relationship.",
    )


@pytest.mark.parametrize("question", AUTHORED_GUIDED_QUESTIONS)
@pytest.mark.parametrize("expected_state", ["CORRECT", "PARTIAL", "WRONG", "STUCK"])
def test_every_authored_guided_question_handles_each_meaningful_student_state(
    monkeypatch: pytest.MonkeyPatch,
    question: AuthoredQuestion,
    expected_state: ExpectedState,
) -> None:
    response_by_state: dict[ExpectedState, str] = {
        "CORRECT": question.correct_response,
        "PARTIAL": question.partial_response,
        "WRONG": question.wrong_response,
        "STUCK": "I don't know",
    }

    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs: object) -> GeneratedQuestionRubric:
            return _rubric(question.question_id)

        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            objective = kwargs["active_objective"]
            assert isinstance(objective, ActiveTeachingObjective)
            return _evaluation(expected_state, objective, question.error_code)

    def build_guided_client(settings: Settings) -> _GuidedClient:
        del settings
        return _GuidedClient()

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        build_guided_client,
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id=question.question_id,
            question=question.question,
            correct_answer=question.canonical_answer,
            answer_spec=AnswerSpec(
                answer_spec_id=f"ANS-{question.question_id}",
                canonical_answer=question.canonical_answer,
                accepted_answers=question.accepted_answers,
                verification_method=question.verification_method,
                explanation_required=(
                    question.verification_method
                    in {
                        "CONCEPT_TEXT_MATCH",
                        "CHOICE_AND_CONCEPT_MATCH",
                        "STRUCTURED_TEXT_MATCH",
                    }
                ),
            ),
            phase_2_prompt_context=Phase2PromptContext(
                target_micro_skill_ids=[question.micro_skill_id],
                support_state={},
                potential_errors=[
                    {
                        "error_code": question.error_code,
                        "description": "Authored misconception for this question.",
                    }
                ],
                support_catalog={},
                current_support=None,
                current_scaffold_step_number=0,
                consecutive_stuck_count=0,
            ),
            student_input=response_by_state[expected_state],
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    actual_state = response.guided_student_state or response.evaluation
    assert actual_state == expected_state
    assert response.attempt_increment == (
        1 if expected_state in {"CORRECT", "WRONG"} else 0
    )
    assert response.selected_error_code == (
        question.error_code if expected_state == "WRONG" else None
    )
    if expected_state in {"PARTIAL", "STUCK"}:
        assert response.student_model_events == []


@pytest.mark.parametrize("question", AUTHORED_GUIDED_QUESTIONS)
def test_low_confidence_voice_never_records_an_authored_guided_attempt(
    question: AuthoredQuestion,
) -> None:
    response = classify_student_response(
        ClassificationRequest(
            question_id=question.question_id,
            question=question.question,
            correct_answer=question.canonical_answer,
            answer_spec=AnswerSpec(
                answer_spec_id=f"ANS-{question.question_id}",
                canonical_answer=question.canonical_answer,
                accepted_answers=question.accepted_answers,
                verification_method=question.verification_method,
                explanation_required=False,
            ),
            phase_2_prompt_context=Phase2PromptContext(
                target_micro_skill_ids=[question.micro_skill_id],
                support_state={},
                potential_errors=[],
                support_catalog={},
                current_support=None,
                current_scaffold_step_number=0,
                consecutive_stuck_count=0,
            ),
            student_input=question.correct_response,
            current_phase="GUIDED_PRACTICE",
            input_source="VOICE",
            transcript_confidence=0.4,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "UNCLEAR"
    assert response.attempt_increment == 0
    assert response.student_model_events == []


def test_topic_1_hybrid_external_envelope_completes_the_contract_pipeline() -> None:
    request = HybridTutorRequest.model_validate(_hybrid_topic_1_envelope())
    rules = _hybrid_enabled_rules()

    evidence = classifier.resolve_hybrid_student_evidence(
        request.student_evidence,
        request.question,
        rules.guided_learning.minimum_voice_transcript_confidence,
        rules.guided_learning.minimum_ocr_confidence,
    )
    semantic = classifier.validate_hybrid_semantic_evaluation(
        request,
        HybridSemanticEvaluation(
            pedagogical_state="PARTIAL",
            completed_components=["ANS-T01-003:COMPONENT:1"],
            current_answer_step_index=1,
            current_answer_step_id="ANS-T01-003:STEP:2",
        ),
    )
    decision = classifier.decide_hybrid_pedagogy(
        request.pedagogical_state,
        request.support_state,
        [],
        rules,
    )
    planner_request = HybridCanvasPlannerRequest(
        turn_id="TURN-003",
        question_id=request.question_id,
        answer_spec=request.answer_spec,
        current_answer_step_index=request.pedagogical_state.current_answer_step_index,
        current_answer_step_id="ANS-T01-003:STEP:1",
        completed_component_ids=request.pedagogical_state.completed_component_ids,
        input_reliability=evidence.input_reliability,
        decision=decision,
        ordered_canvas_memory=request.ordered_canvas_memory,
        authored_support_content=[],
        confirmed_tutor_anchors=[],
        approved_answer_reveal=False,
        active_action_ids=[],
    )
    actions = classifier.plan_hybrid_canvas_pedagogy(planner_request, rules)
    wording = classifier.validate_hybrid_tutor_wording(
        "Look at the part I highlighted. What changes?",
        actions,
        request.answer_spec.canonical_answer,
        rules,
    )

    assert evidence.resolved_student_meaning == "s + 6"
    assert semantic.completed_components == ["ANS-T01-003:COMPONENT:1"]
    assert decision.strategy == "AFFIRM_AND_ISOLATE"
    assert actions[0].target_object_id == "student-score-note"
    assert wording == "Look at the part I highlighted. What changes?"


def test_topic_1_hybrid_stuck_envelope_uses_only_authored_support() -> None:
    payload = _hybrid_topic_1_envelope()
    support_state = payload["support_state"]
    pedagogical_state = payload["pedagogical_state"]
    assert isinstance(support_state, dict)
    assert isinstance(pedagogical_state, dict)
    support_state["consecutive_stuck_count"] = 1
    pedagogical_state["student_state"] = "STUCK"
    request = HybridTutorRequest.model_validate(payload)
    rules = _hybrid_enabled_rules()
    support = HybridAuthoredSupportContent(
        source_id="SUPPORT-T01-HINT-01",
        support_action="HINT",
        text="Look at what changes in the score.",
    )

    decision = classifier.decide_hybrid_pedagogy(
        request.pedagogical_state,
        request.support_state,
        [support],
        rules,
    )
    actions = classifier.plan_hybrid_canvas_pedagogy(
        HybridCanvasPlannerRequest(
            turn_id="TURN-004",
            question_id=request.question_id,
            answer_spec=request.answer_spec,
            current_answer_step_index=request.pedagogical_state.current_answer_step_index,
            current_answer_step_id="ANS-T01-003:STEP:1",
            completed_component_ids=request.pedagogical_state.completed_component_ids,
            input_reliability="RELIABLE",
            decision=decision,
            ordered_canvas_memory=request.ordered_canvas_memory,
            authored_support_content=[support],
            confirmed_tutor_anchors=[],
            approved_answer_reveal=False,
            active_action_ids=[],
        ),
        rules,
    )

    assert decision.support_id == "SUPPORT-T01-HINT-01"
    assert actions[0].source_id == "SUPPORT-T01-HINT-01"
    assert actions[0].type == "SHOW_CUE"
