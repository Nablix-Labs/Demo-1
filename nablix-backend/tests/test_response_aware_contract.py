"""Replay assessed contributions across evidence validation and support routing.

These tests validate the service contract, not the quality of live interpretation.
"""
import pytest

from app.ai_engine.classifier import validate_guided_evaluation
from app.ai_engine.classifier_config import load_classifier_rules
from app.core.exceptions import AdapterError
from app.models.adapters import TutorResult
from app.models.guided_learning import (
    ActiveTeachingObjective, GeneratedConcept, GeneratedQuestionRubric,
    GuidedEvaluation, StudentContribution,
    GuidedRescue, TutorSolved, GuidedWorkedPresentation,
)
from app.models.session import SessionRecord
from app.services import interaction_service
from app.services.rescue_presentation import active_rescue_from
from app.services.interaction_service import (
    _guided_attempt_event_type, _is_support_failure, _is_unresolved_scaffold_turn,
)


@pytest.mark.parametrize("kind", [
    "ACKNOWLEDGEMENT", "EXPLANATION_REQUEST", "UNCLEAR_INPUT", "EXPRESSED_DIFFICULTY",
])
def test_non_attempt_preserves_prior_evidence_without_support(kind: str) -> None:
    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True}
    )})
    objective = ActiveTeachingObjective(
        objective_type="EXPLAIN_REASONING", target_concept_ids=["ANSWER_EXPLANATION"],
        confirmed_concept_ids=["ANSWER_SELECTION"], missing_concept_ids=["ANSWER_EXPLANATION"],
    )
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004", required_concepts=[
            GeneratedConcept(concept_id="ANSWER_SELECTION", description="Choose a rule", required=True),
            GeneratedConcept(concept_id="ANSWER_EXPLANATION", description="Explain generality", required=True),
        ], completion_rule="ALL_REQUIRED_CONCEPTS", cache_key="replay", prompt_version="replay",
    )
    contribution = StudentContribution.model_validate({
        "kind": kind, "assessment": "NOT_ASSESSED", "error_category": None,
        "error_description": None, "identified_difficulty": None, "learner_question": None,
        "explained_idea": None, "generated_support_text": None, "support_relevance": "NOT_NEEDED",
    })
    candidate = GuidedEvaluation(
        contribution=contribution, student_state="PARTIAL",
        newly_confirmed_concept_ids=[], preserved_concept_ids=["ANSWER_SELECTION"],
        contradicted_concept_ids=[], missing_concept_ids=["ANSWER_EXPLANATION"],
        selected_error_code=None, confidence=0.98, next_objective=objective,
        tutor_message="Which part of the instruction would you like me to explain?",
        tutor_message_voice="Which part of the instruction would you like me to explain?",
    )
    result = validate_guided_evaluation(candidate, rubric, objective, [], rules)
    assert result.student_state in {"STUCK", "UNCLEAR"}
    assert result.next_objective == objective
    assert result.preserved_concept_ids == ["ANSWER_SELECTION"]
    tutor = TutorResult.model_construct(
        contribution=result.contribution, guided_student_state=result.student_state,
        evaluation="NO_ATTEMPT", intent="EXPRESSING_CONFUSION",
    )
    assert _guided_attempt_event_type(tutor, rules) is None
    assert not _is_support_failure(tutor)
    assert not _is_unresolved_scaffold_turn(tutor)
    with pytest.raises(AdapterError, match="non-attempt"):
        validate_guided_evaluation(candidate.model_copy(update={
            "newly_confirmed_concept_ids": ["ANSWER_EXPLANATION"],
        }), rubric, objective, [], rules)


@pytest.mark.parametrize("assessment,expected_event", [
    ("INCORRECT", "INCORRECT_ATTEMPT"), ("INCOMPLETE", None),
])
def test_partial_evidence_only_advances_support_when_it_contains_an_error(
    assessment: str, expected_event: str | None,
) -> None:
    incorrect = assessment == "INCORRECT"
    contribution = StudentContribution.model_validate({
        "kind": "MATHEMATICAL_ATTEMPT", "assessment": assessment,
        "error_category": "VARIABLE_CONSTANT" if incorrect else None,
        "error_description": "The fixed amount in the proposed rule differs from the examples." if incorrect else None,
        "identified_difficulty": None, "learner_question": None, "explained_idea": None,
        "generated_support_text": "Compare the visible repeated amount." if incorrect else None,
        "support_relevance": "UNMAPPED" if incorrect else "NOT_NEEDED",
    })
    tutor = TutorResult.model_construct(
        contribution=contribution, guided_student_state="PARTIAL",
        evaluation="PARTIALLY_CORRECT", intent="SUBMITTING_ANSWER",
    )
    assert _guided_attempt_event_type(tutor, load_classifier_rules()) == expected_event
    assert _is_support_failure(tutor) is incorrect
    assert _is_unresolved_scaffold_turn(tutor) is incorrect


def test_incorrect_expression_keeps_valid_evidence_and_moves_to_an_unresolved_concept() -> None:
    previous = ActiveTeachingObjective(
        objective_type="EXPLAIN_REASONING",
        target_concept_ids=["ANSWER_SELECTION"],
        confirmed_concept_ids=[],
        missing_concept_ids=["ANSWER_SELECTION", "FIXED_AMOUNT"],
    )
    evaluation = GuidedEvaluation(
        contribution=StudentContribution.model_validate({
            "kind": "MATHEMATICAL_ATTEMPT", "assessment": "INCORRECT",
            "error_category": "EXPRESSION_STRUCTURE",
            "error_description": "The repeated amount in the expression does not match the examples.",
            "identified_difficulty": None, "learner_question": "Why is my rule wrong?",
            "explained_idea": None, "generated_support_text": None,
            "support_relevance": "MATCHED",
        }),
        student_state="WRONG", newly_confirmed_concept_ids=["ANSWER_SELECTION"],
        preserved_concept_ids=[], contradicted_concept_ids=["FIXED_AMOUNT"],
        missing_concept_ids=["FIXED_AMOUNT"], selected_error_code="ERROR_FIXED_AMOUNT",
        confidence=0.96,
        next_objective=ActiveTeachingObjective(
            objective_type="EXPLAIN_CONCEPT", target_concept_ids=[],
            confirmed_concept_ids=["ANSWER_SELECTION"], missing_concept_ids=["FIXED_AMOUNT"],
        ),
        tutor_message="Compare the number after the plus sign in 3 + 5, 9 + 5, and 14 + 5.",
        tutor_message_voice="Compare the number after the plus sign in 3 plus 5, 9 plus 5, and 14 plus 5.",
    )

    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True},
    )})
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-001", required_concepts=[
            GeneratedConcept(concept_id="ANSWER_SELECTION", description="Uses the variable", required=True),
            GeneratedConcept(concept_id="FIXED_AMOUNT", description="Matches the repeated amount", required=True),
        ], completion_rule="ALL_REQUIRED_CONCEPTS", cache_key="replay", prompt_version="replay",
    )
    validated = validate_guided_evaluation(
        evaluation, rubric, previous, [{"error_code": "ERROR_FIXED_AMOUNT"}], rules,
    )
    objective = validated.next_objective

    assert objective is not None
    assert objective.confirmed_concept_ids == ["ANSWER_SELECTION"]
    assert objective.missing_concept_ids == ["FIXED_AMOUNT"]
    assert objective.target_concept_ids == ["FIXED_AMOUNT"]


def test_generated_walkthrough_is_persistable_and_rejects_early_reveal(monkeypatch: pytest.MonkeyPatch) -> None:
    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True},
    )})
    rescue = GuidedRescue(
        rescue_type="TUTOR_SOLVED", micro_skill_id="T01.M1", parallel_example=None,
        tutor_solved=TutorSolved(explanation="Combine the parts.", final_answer="n + 5",
                                 answer_steps=["Compare the examples.", "n + 5"]),
    )
    active = active_rescue_from("Q-T01-001", rescue, "n + 5", "TEST-WORKED")
    session = SessionRecord.model_construct(question_id="Q-T01-001", current_question="3 + 5, 9 + 5, 14 + 5")
    presentation = GuidedWorkedPresentation.model_validate({"steps": [
        {"expression": "3 + 5, 9 + 5, 14 + 5", "annotation": "The first numbers differ while the added amount repeats."},
        {"expression": "n + 5", "annotation": "The letter represents each starting number and five is added."},
    ]})

    class PresentationClient:
        def write_guided_worked_presentation(self, support: dict[str, object], system_prompt: str) -> GuidedWorkedPresentation:
            assert support["authorised_support"] == rescue.model_dump()
            assert system_prompt == rules.guided_learning.response_aware_worked_prompt
            return presentation

    monkeypatch.setattr(interaction_service, "build_openai_ai_engine_client", lambda settings: PresentationClient())
    updated = interaction_service._response_aware_worked_rescue(session, active, rescue, "n + 5", rules)
    assert updated is not None
    assert updated.steps[-1] == "n + 5\nThe letter represents each starting number and five is added."
    assert updated.current_step_index == 1
    assert len(updated.steps) == 2
    presentation = GuidedWorkedPresentation.model_validate({"steps": [
        {"expression": "n + 5", "annotation": "This is the answer."},
        {"expression": "n + 5", "annotation": "Five is added to the starting value."},
    ]})
    with pytest.raises(AdapterError, match="before authorisation"):
        interaction_service._response_aware_worked_rescue(session, active, rescue, "n + 5", rules)
