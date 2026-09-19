"""Replay assessed contributions across evidence validation and support routing.

These tests validate the service contract, not the quality of live interpretation.
"""
import pytest
from fastapi import HTTPException

from app.ai_engine.classifier import (
    ClassificationRequest,
    accept_reliable_canvas_submission,
    build_guided_tutor_response,
    current_learner_response,
    required_response_aware_learner_action,
    request_with_reliable_canvas_evidence,
    response_aware_fallback_message,
    validate_guided_evaluation,
    validate_response_aware_submission,
)
from app.ai_engine.classifier_config import load_classifier_rules
from app.ai_engine.openai_client import (
    OpenAIGuidedWording,
    guided_assessment_schema,
    guided_evaluation_schema,
    normalize_assessment_contribution_payload,
    openai_strict_schema,
)
from app.ai_engine.schemas import SafetyCheck
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, TutorResult
from app.models.guided_learning import (
    ActiveTeachingObjective, GeneratedConcept, GeneratedQuestionRubric,
    GuidedEvaluation, StudentContribution,
    GuidedRescue, TutorSolved, GuidedWorkedPresentation,
)
from app.models.session import SessionRecord
from app.models.student_model_session import AnswerSpec
from app.services import interaction_service
from app.services.rescue_presentation import active_rescue_from
from app.services.interaction_service import (
    _guided_attempt_event_type, _is_support_failure, _is_unresolved_scaffold_turn,
    _verified_canvas_completion_event_type,
)


@pytest.mark.parametrize("kind", [
    "ACKNOWLEDGEMENT", "EXPLANATION_REQUEST", "TASK_CLARIFICATION",
    "UNCLEAR_INPUT", "EXPRESSED_DIFFICULTY",
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
        "explained_idea": "general rule" if kind == "EXPLANATION_REQUEST" else None,
        "generated_support_text": None, "support_relevance": "NOT_NEEDED",
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


def test_verified_canvas_acknowledgement_becomes_a_correct_progression_event() -> None:
    contribution = StudentContribution.model_validate({
        "kind": "ACKNOWLEDGEMENT",
        "assessment": "NOT_ASSESSED",
        "error_category": None,
        "error_description": None,
        "identified_difficulty": None,
        "learner_question": None,
        "explained_idea": None,
        "generated_support_text": None,
        "support_relevance": "NOT_NEEDED",
    })
    tutor = TutorResult.model_construct(
        contribution=contribution,
        question_completed=True,
        answer_value_confirmed=True,
    )
    context = AdapterContext.model_construct(
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=True,
    )

    assert _verified_canvas_completion_event_type(tutor, context) == "CORRECT_ATTEMPT"


def test_unverified_canvas_acknowledgement_does_not_progress() -> None:
    contribution = StudentContribution.model_validate({
        "kind": "ACKNOWLEDGEMENT",
        "assessment": "NOT_ASSESSED",
        "error_category": None,
        "error_description": None,
        "identified_difficulty": None,
        "learner_question": None,
        "explained_idea": None,
        "generated_support_text": None,
        "support_relevance": "NOT_NEEDED",
    })
    tutor = TutorResult.model_construct(
        contribution=contribution,
        question_completed=True,
        answer_value_confirmed=True,
    )
    context = AdapterContext.model_construct(
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=False,
    )

    assert _verified_canvas_completion_event_type(tutor, context) is None


def test_canvas_completion_does_not_turn_task_clarification_into_an_attempt() -> None:
    contribution = StudentContribution.model_validate({
        "kind": "TASK_CLARIFICATION",
        "assessment": "NOT_ASSESSED",
        "error_category": None,
        "error_description": None,
        "identified_difficulty": None,
        "learner_question": "What do I do now?",
        "explained_idea": None,
        "generated_support_text": None,
        "support_relevance": "NOT_NEEDED",
    })
    tutor = TutorResult.model_construct(
        contribution=contribution,
        question_completed=True,
        answer_value_confirmed=True,
    )
    context = AdapterContext.model_construct(
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=True,
    )

    assert _verified_canvas_completion_event_type(tutor, context) is None


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
    active = active_rescue_from("Q-T01-001", rescue, "TEST-WORKED")
    session = SessionRecord.model_construct(
        question_id="Q-T01-001", current_question="3 + 5, 9 + 5, 14 + 5",
        active_guided_rescue=None,
    )
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
    updated = interaction_service._presented_rescue(
        session, "Q-T01-001", rescue, "n + 5", "TEST-WORKED", rules,
    )
    assert updated is not None
    assert updated.steps[-1] == "n + 5\nThe letter represents each starting number and five is added."
    assert updated.current_step_index == 1
    assert len(updated.steps) == 2
    presentation = GuidedWorkedPresentation.model_validate({"steps": [
        {"expression": "n + 5", "annotation": "This is the answer."},
        {"expression": "n + 5", "annotation": "Five is added to the starting value."},
    ]})
    with pytest.raises(HTTPException, match="before authorisation"):
        interaction_service._presented_rescue(
            session, "Q-T01-001", rescue, "n + 5", "TEST-WORKED", rules,
        )


def test_strict_output_cannot_mix_correctness_and_corrective_support() -> None:
    original = guided_evaluation_schema()
    schema = openai_strict_schema(original)
    assert "properties" in original["$defs"]["StudentContribution"]
    variants = schema["$defs"]["StudentContribution"]["anyOf"]
    assert len(variants) == 4
    for variant in variants:
        props = variant["properties"]
        assessments = props["assessment"]["enum"]
        if "INCORRECT" not in assessments:
            assert props["support_relevance"]["enum"] == ["NOT_NEEDED"]
            assert props["generated_support_text"]["type"] == "null"
            assert props["generated_visual_rows"]["type"] == "null"
        elif props["support_relevance"]["enum"] == ["MATCHED"]:
            assert props["generated_support_text"]["type"] == "null"
        else:
            assert props["generated_support_text"]["type"] == "string"
            assert props["generated_visual_rows"]["type"] == "array"
            assert props["generated_visual_rows"]["minItems"] == 2
    original["$defs"]["StudentContribution"]["properties"]["support_relevance"]["enum"] = [
        "NOT_NEEDED", "UNMAPPED", "MISMATCHED",
    ]
    without_catalog = openai_strict_schema(original)
    assert len(without_catalog["$defs"]["StudentContribution"]["anyOf"]) == 3


def test_production_assessment_schema_cannot_mix_correctness_and_support() -> None:
    schema = openai_strict_schema(guided_assessment_schema())
    variants = schema["$defs"]["GuidedAssessmentContribution"]["anyOf"]

    assert len(variants) == 4
    for variant in variants:
        properties = variant["properties"]
        assessments = properties["assessment"]["enum"]
        if "INCORRECT" not in assessments:
            assert properties["support_relevance"]["enum"] == ["NOT_NEEDED"]


def test_production_assessment_recovers_evidence_from_irrelevant_support_metadata() -> None:
    payload = normalize_assessment_contribution_payload({
        "contribution": {
            "kind": "MATHEMATICAL_ATTEMPT",
            "assessment": "CORRECT",
            "error_category": "VARIABLE_CONSTANT",
            "error_description": "unused",
            "support_relevance": "MATCHED",
        },
        "newly_confirmed_concept_ids": ["GENERAL_RULE_ADD_FIVE"],
    })
    contribution = payload["contribution"]

    assert isinstance(contribution, dict)
    assert contribution["error_category"] is None
    assert contribution["error_description"] is None
    assert contribution["support_relevance"] == "NOT_NEEDED"
    assert payload["newly_confirmed_concept_ids"] == ["GENERAL_RULE_ADD_FIVE"]


def test_canvas_submission_state_cannot_claim_matching_without_canvas_evidence() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write the general rule.",
        correct_answer="n + 5",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="n + 5",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="n + 5",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
    )
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="CORRECT",
        newly_confirmed_concept_ids=["GENERAL_RULE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MATCHING",
        tutor_message="The rule is complete.",
        tutor_message_voice="The rule is complete.",
    )

    with pytest.raises(AdapterError, match="reliable complete canvas evidence"):
        validate_response_aware_submission(evaluation, request)

    missing = validate_response_aware_submission(
        evaluation.model_copy(update={"submission_state": "MISSING"}),
        request,
    )
    assert missing.submission_state == "MISSING"


def test_incomplete_canvas_question_does_not_request_submission_yet() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write the general rule.",
        correct_answer="n + 5",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="n + 5",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="5 stays fixed",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
    )
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["FIXED_VALUE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE"],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="NOT_REQUIRED",
        tutor_message="You identified the fixed value.",
        tutor_message_voice="You identified the fixed value.",
    )

    assert validate_response_aware_submission(evaluation, request).submission_state == "NOT_REQUIRED"
    assert required_response_aware_learner_action(evaluation) == "CONTINUE"


def test_conflicting_canvas_work_can_request_rewrite_before_math_is_complete() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write the general rule.",
        correct_answer="n + 5",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="n + 5",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="h + 5",
        current_phase="GUIDED_PRACTICE",
        input_source="CANVAS",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
        has_canvas_evidence=True,
    )
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=["GENERAL_RULE"],
        missing_concept_ids=["GENERAL_RULE"],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MISMATCHED",
        tutor_message="Check the required letter.",
        tutor_message_voice="Check the required letter.",
    )

    assert validate_response_aware_submission(evaluation, request).submission_state == "MISMATCHED"
    assert required_response_aware_learner_action(evaluation) == "REWRITE"


def test_voice_correction_keeps_current_words_separate_from_conflicting_canvas_work() -> None:
    rules = load_classifier_rules()
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="A player starts with score s and gains 6 bonus points. Write the new-score rule.",
        correct_answer="s + 6",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="s + 6",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="It is s plus 6.",
        current_phase="GUIDED_PRACTICE",
        input_source="VOICE",
        transcript_confidence=0.95,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
        has_canvas_evidence=True,
        canvas_ocr_text="n + 6",
        canvas_ocr_confidence=0.98,
    )
    merged = request_with_reliable_canvas_evidence(request, rules)
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="CORRECT",
        newly_confirmed_concept_ids=["GENERAL_RULE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MISMATCHED",
        tutor_message="Please update the rule on the canvas.",
        tutor_message_voice="Please update the rule on the canvas.",
    )

    assert current_learner_response(merged) == "It is s plus 6."
    assert "n + 6" in merged.student_input
    assert validate_response_aware_submission(evaluation, merged).submission_state == "MISMATCHED"
    assert required_response_aware_learner_action(evaluation) == "REWRITE"


def test_reliable_canvas_answer_completes_an_acknowledgement_turn() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write the general rule.",
        correct_answer="n + 5",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="n + 5",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="I have written it.",
        current_phase="GUIDED_PRACTICE",
        input_source="VOICE",
        transcript_confidence=0.95,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=True,
    )
    evaluation = GuidedEvaluation(
        contribution=StudentContribution.model_validate({
            "kind": "ACKNOWLEDGEMENT",
            "assessment": "NOT_ASSESSED",
            "error_category": None,
            "error_description": None,
            "identified_difficulty": None,
            "learner_question": None,
            "explained_idea": None,
            "generated_support_text": None,
            "support_relevance": "NOT_NEEDED",
        }),
        student_state="STUCK",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=["FIXED_VALUE"],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_ADD_FIVE"],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MISMATCHED",
        tutor_message="Please rewrite the rule.",
        tutor_message_voice="Please rewrite the rule.",
    )

    completed = accept_reliable_canvas_submission(evaluation, request)

    assert completed.student_state == "CORRECT"
    assert completed.submission_state == "MATCHING"
    assert completed.newly_confirmed_concept_ids == ["GENERAL_RULE_ADD_FIVE"]
    assert completed.missing_concept_ids == []
    assert validate_response_aware_submission(completed, request) is completed


def test_matching_canvas_expression_wins_over_earlier_conflicting_work() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write the general rule.",
        correct_answer="n + 5",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="n + 5",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        student_input="n plus 5",
        current_phase="GUIDED_PRACTICE",
        input_source="CANVAS",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=True,
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=True,
    )
    evaluation = GuidedEvaluation(
        contribution=StudentContribution.model_validate({
            "kind": "MATHEMATICAL_ATTEMPT",
            "assessment": "CORRECT",
            "error_category": None,
            "error_description": None,
            "identified_difficulty": None,
            "learner_question": None,
            "explained_idea": None,
            "generated_support_text": None,
            "support_relevance": "NOT_NEEDED",
        }),
        student_state="CORRECT",
        newly_confirmed_concept_ids=["GENERAL_RULE_ADD_FIVE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MISMATCHED",
        tutor_message="Please remove the earlier rule.",
        tutor_message_voice="Please remove the earlier rule.",
    )

    completed = accept_reliable_canvas_submission(evaluation, request)

    assert completed.submission_state == "MATCHING"
    assert required_response_aware_learner_action(completed) == "CONTINUE"


def test_verified_canvas_completes_a_partial_voice_answer_when_not_required() -> None:
    request = ClassificationRequest(
        question_id="REPLAY",
        question_type="SHORT_RESPONSE",
        question="Write p × p × q in compact algebraic notation.",
        correct_answer="p²q",
        answer_spec=AnswerSpec(
            answer_spec_id="REPLAY",
            canonical_answer="p²q",
            accepted_answers=["p^2q"],
            verification_method="EXACT_NOTATION_MATCH",
            explanation_required=False,
        ),
        student_input="The power is 2.",
        current_phase="GUIDED_PRACTICE",
        input_source="VOICE",
        transcript_confidence=0.95,
        attempt_count=0,
        current_hint_level=None,
        canvas_submission_required=False,
        has_canvas_evidence=True,
        canvas_solution_complete_candidate=True,
    )
    evaluation = GuidedEvaluation(
        contribution=StudentContribution.model_validate({
            "kind": "MATHEMATICAL_ATTEMPT",
            "assessment": "INCOMPLETE",
            "error_category": None,
            "error_description": None,
            "identified_difficulty": None,
            "learner_question": None,
            "explained_idea": None,
            "generated_support_text": None,
            "support_relevance": "NOT_NEEDED",
        }),
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["COMPACT_PRODUCT_NOTATION"],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="NOT_REQUIRED",
        tutor_message="Write the compact notation.",
        tutor_message_voice="Write the compact notation.",
    )

    completed = accept_reliable_canvas_submission(evaluation, request)

    assert completed.student_state == "CORRECT"
    assert completed.newly_confirmed_concept_ids == ["COMPACT_PRODUCT_NOTATION"]
    assert completed.missing_concept_ids == []
    assert completed.submission_state == "NOT_REQUIRED"


@pytest.mark.parametrize(
    ("submission_state", "expected_action"),
    [
        ("MISSING", "WRITE"),
        ("MISMATCHED", "REWRITE"),
        ("UNCLEAR", "REWRITE"),
        ("NOT_REQUIRED", "CONTINUE"),
        ("MATCHING", "CONTINUE"),
    ],
)
def test_submission_state_authorizes_one_writer_action(
    submission_state: str,
    expected_action: str,
) -> None:
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="CORRECT",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state=submission_state,
        tutor_message="Continue.",
        tutor_message_voice="Continue.",
    )

    assert required_response_aware_learner_action(evaluation) == expected_action


def test_guided_writer_requires_structured_learner_action() -> None:
    schema = OpenAIGuidedWording.model_json_schema()
    properties = schema["properties"]

    assert properties["learner_action"]["enum"] == [
        "CONTINUE",
        "WRITE",
        "REWRITE",
        "CLARIFY",
    ]


def test_completed_canvas_turn_never_falls_back_to_generic_wording() -> None:
    evaluation = GuidedEvaluation(
        contribution=None,
        student_state="CORRECT",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=[],
        selected_error_code=None,
        confidence=0.98,
        next_objective=None,
        submission_state="MISSING",
        tutor_message="unused",
        tutor_message_voice="unused",
    )

    assert response_aware_fallback_message(
        evaluation,
        load_classifier_rules(),
    ) == "You have the rule. Now write it on the canvas, then press Check."


def test_model_evidence_survives_wrong_rule_then_correct_rule_canvas_handoff() -> None:
    rules = load_classifier_rules()
    rules = rules.model_copy(update={"guided_learning": rules.guided_learning.model_copy(
        update={"response_aware_enabled": True},
    )})
    ids = ["CHANGING_VALUE", "OPERATION", "FIXED_VALUE"]
    rubric = GeneratedQuestionRubric(
        question_id="REPLAY", required_concepts=[
            GeneratedConcept(concept_id=concept_id, description=concept_id, required=True) for concept_id in ids
        ], completion_rule="ALL_REQUIRED_CONCEPTS", cache_key="replay", prompt_version="replay",
    )
    request = ClassificationRequest(
        question_id="REPLAY", question_type="SHORT_RESPONSE",
        question="3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number. Write the general rule.",
        correct_answer="n + 5", student_input="its n+6", current_phase="GUIDED_PRACTICE",
        input_source="TEXT", transcript_confidence=None, attempt_count=0, current_hint_level=None,
        canvas_submission_required=True,
        answer_spec=AnswerSpec(answer_spec_id="REPLAY", canonical_answer="n + 5", accepted_answers=[],
                               verification_method="STRUCTURED_TEXT_MATCH", explanation_required=False),
    )
    objective = ActiveTeachingObjective(objective_type="EXPLAIN_CONCEPT", target_concept_ids=["FIXED_VALUE"],
                                        confirmed_concept_ids=ids[:2], missing_concept_ids=["FIXED_VALUE"])
    incorrect = GuidedEvaluation(
        contribution=StudentContribution(kind="MATHEMATICAL_ATTEMPT", assessment="INCORRECT",
            error_category="VARIABLE_CONSTANT", error_description="Repeated amount is incorrect.",
            identified_difficulty=None, learner_question=None, explained_idea=None,
            generated_support_text=None, support_relevance="MATCHED"),
        student_state="WRONG", newly_confirmed_concept_ids=ids[:2], preserved_concept_ids=[],
        contradicted_concept_ids=["FIXED_VALUE"], missing_concept_ids=["FIXED_VALUE"],
        selected_error_code="FIXED_AMOUNT", confidence=0.98, next_objective=objective,
        tutor_message="Compare your added amount with the amount after the plus sign in each example.",
        tutor_message_voice="Compare your added amount with the amount after the plus sign in each example.",
    )
    safety = SafetyCheck(passed=True, flag_type=None, action_taken=None)
    wrong = build_guided_tutor_response(request, rules, safety, rubric, incorrect, objective)
    state = wrong.guided_teaching_state
    assert state is not None
    assert state.active_component_id == "FIXED_VALUE"
    assert {claim.concept_id for claim in state.last_turn_evidence} == set(ids)
    assert state.confirmed_component_ids == ids[:2]
    request = request.model_copy(update={"student_input": "n+5", "guided_teaching_state": state,
                                         "active_teaching_objective": objective})
    correct = incorrect.model_copy(update={
        "contribution": StudentContribution(kind="MATHEMATICAL_ATTEMPT", assessment="CORRECT",
            error_category=None, error_description=None, identified_difficulty=None, learner_question=None,
            explained_idea=None, generated_support_text=None, support_relevance="NOT_NEEDED"),
        "student_state": "CORRECT", "newly_confirmed_concept_ids": ["FIXED_VALUE"],
        "preserved_concept_ids": ids[:2], "contradicted_concept_ids": [], "missing_concept_ids": [],
        "selected_error_code": None, "next_objective": None,
        "submission_state": "MISSING",
        "tutor_message": "Your rule matches the examples. Write it on the canvas, then press Check.",
        "tutor_message_voice": "Your rule matches the examples. Write it on the canvas, then press Check.",
    })
    result = build_guided_tutor_response(request, rules, safety, rubric, correct, None)
    assert result.requires_written_math_evidence
    assert not result.question_completed
    assert result.guided_teaching_state is not None
    assert set(result.guided_teaching_state.confirmed_component_ids) == set(ids)
    assert all(claim.status == "DEMONSTRATED" for claim in result.guided_teaching_state.evidence_ledger)
    assert result.tutor_message == correct.tutor_message
