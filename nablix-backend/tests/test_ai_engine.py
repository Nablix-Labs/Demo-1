import json
import logging
from typing import cast

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
from app.ai_engine.schemas import (
    ActiveScaffoldState,
    CanvasTextRegion,
    ExplainAgainRequest,
    OpenAIExplainAgainMessage,
    RecordedMisconception,
    VisibleVisualCue,
)
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
    SpatialMathToken,
    StudentModelResult,
    TutorEngineRequest,
)
from app.models.student_model_session import AnswerSpec
from app.models.guided_learning import (
    ActiveTeachingObjective,
    FocusedComponentEvidence,
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedEvaluation,
    GuidedTeachingState,
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


@pytest.mark.parametrize("student_input", ["what", "idk", "I have no idea", "are u stupid"])
def test_guided_confusion_uses_semantic_tutor_evaluation(
    monkeypatch,
    student_input: str,
) -> None:
    class _EvaluationClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            return GuidedEvaluation(
                student_state="STUCK",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["OPERATION", "EXPANDED_MEANING"],
                selected_error_code=None,
                confidence=0.9,
                next_objective=None,
                tutor_message=(
                    "That makes sense. Let’s use the expression in front of us: "
                    "what does the plus sign tell us to do?"
                ),
                tutor_message_voice=(
                    "That makes sense. Let’s use the expression in front of us: "
                    "what does the plus sign tell us to do?"
                ),
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _EvaluationClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-002",
            question_type="MULTI_PART_SHORT_RESPONSE",
            question="In m + 7, identify the changing quantity, fixed value, and operation.",
            correct_answer="m; 7; addition",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-T02-002",
                canonical_answer="m; 7; addition",
                accepted_answers=[],
                verification_method="STRUCTURED_TEXT_MATCH",
                explanation_required=True,
            ),
            phase_2_prompt_context=_guided_context(0),
            generated_question_rubric=_guided_rubric(),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "STUCK"
    assert response.intent == "EXPRESSING_CONFUSION"
    assert response.attempt_increment == 0
    assert "what does the plus sign" in response.tutor_message
    assert "one part at a time" not in response.tutor_message


def test_guided_component_question_stays_specific_after_confusion_and_wrong_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EvaluationClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            return GuidedEvaluation(
                student_state="STUCK",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
                selected_error_code=None,
                confidence=0.9,
                next_objective=None,
                tutor_message=(
                    "That is understandable. Which part can take different "
                    "possible values?"
                ),
                tutor_message_voice=(
                    "That is understandable. Which part can take different "
                    "possible values?"
                ),
            )

    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-COMPONENTS",
        required_concepts=[
            GeneratedConcept(concept_id="CHANGING_VALUE", description="m changes", required=True),
            GeneratedConcept(concept_id="FIXED_VALUE", description="7 stays fixed", required=True),
            GeneratedConcept(concept_id="OPERATION", description="addition", required=True),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="component-rubric",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _EvaluationClient(),
    )
    request = ClassificationRequest(
        question_id="Q-T01-COMPONENTS",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="In m + 7, identify the changing quantity, the fixed value and the operation.",
        correct_answer="m; 7; addition",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-COMPONENTS",
            canonical_answer="m; 7; addition",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=True,
        ),
        phase_2_prompt_context=_guided_context(0),
        generated_question_rubric=rubric,
        active_teaching_objective=objective,
        student_input="I do not understand",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
    )
    confused = classify_student_response(request)

    assert confused.guided_student_state == "STUCK"
    assert confused.tutor_message.endswith("Which part can take different possible values?")
    assert confused.guided_teaching_state is not None

    wrong = classify_student_response(
        request.model_copy(
            update={
                "student_input": "the changing quantity is 7",
                "guided_teaching_state": confused.guided_teaching_state,
                "active_teaching_objective": confused.active_teaching_objective,
            }
        )
    )

    assert wrong.guided_student_state == "WRONG"
    assert "the changing quantity is the letter" in wrong.tutor_message
    assert wrong.tutor_message.endswith("Which part can take different possible values?")


def test_guided_evaluator_context_preserves_active_step_and_support_state() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-COMPONENTS",
        required_concepts=[
            GeneratedConcept(concept_id="CHANGING_VALUE", description="m changes", required=True),
            GeneratedConcept(concept_id="FIXED_VALUE", description="7 stays fixed", required=True),
            GeneratedConcept(concept_id="OPERATION", description="addition", required=True),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="component-rubric",
        prompt_version="1.0.0",
    )
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["FIXED_VALUE"],
        confirmed_concept_ids=["CHANGING_VALUE"],
        missing_concept_ids=["FIXED_VALUE", "OPERATION"],
    )
    request = ClassificationRequest(
        question_id="Q-T01-COMPONENTS",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="In m + 7, identify the changing quantity, the fixed value and the operation.",
        correct_answer="m; 7; addition",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-COMPONENTS",
            canonical_answer="m; 7; addition",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=True,
        ),
        phase_2_prompt_context=_guided_context(2).model_copy(
            update={
                "support_state": {"hint_level": 2},
                "current_support": {"support_type": "VISUAL_CUE"},
                "current_scaffold_step_number": 1,
            }
        ),
        generated_question_rubric=rubric,
        active_teaching_objective=objective,
        guided_teaching_state=GuidedTeachingState(
            question_id="Q-T01-COMPONENTS",
            objective_component_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
            confirmed_component_ids=["CHANGING_VALUE"],
            missing_component_ids=["FIXED_VALUE", "OPERATION"],
            active_component_id="FIXED_VALUE",
            last_tutor_question_type="COMPONENT",
            selected_option_id=None,
            awaiting_response=True,
            active_step_id="FIXED_VALUE",
            teaching_step_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
        ),
        student_input="7 stays fixed",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=2,
        current_hint_level=2,
    )

    context = classifier.guided_tutor_context_for(request, rubric, objective)

    assert context.active_step_id == "FIXED_VALUE"
    assert context.active_tutor_question == "Which value stays fixed in this rule?"
    assert [step.step_id for step in context.ordered_teaching_steps] == [
        "CHANGING_VALUE",
        "FIXED_VALUE",
        "OPERATION",
    ]
    assert context.confirmed_concept_ids == ["CHANGING_VALUE"]
    assert context.missing_concept_ids == ["FIXED_VALUE", "OPERATION"]
    assert context.current_support == {"support_type": "VISUAL_CUE"}
    assert context.current_scaffold_step_number == 1
    assert context.consecutive_stuck_count == 2


def test_new_score_rule_uses_the_same_guided_rule_controller() -> None:
    request = ClassificationRequest(
        question_id="Q-T01-SCORE",
        question_type="SHORT_RESPONSE",
        question="A player starts with score s and gains 6 bonus points. Write the new-score rule.",
        correct_answer="s + 6",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-SCORE",
            canonical_answer="s + 6",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        student_input="s minus six",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
    )
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-SCORE",
        required_concepts=[
            GeneratedConcept(concept_id="GENERAL_RULE", description="new score rule", required=True)
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="score-rule",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)

    evaluation = classifier.deterministic_teaching_step_evaluation(
        request,
        rubric,
        objective,
    )

    assert evaluation is not None
    assert evaluation.student_state == "WRONG"
    assert "add, not subtract" in evaluation.tutor_message
    assert "falls" not in evaluation.tutor_message


def test_guided_follow_up_replaces_an_unrelated_llm_question() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-SCORE",
        required_concepts=[
            GeneratedConcept(concept_id="GENERAL_RULE", description="new score rule", required=True)
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="score-rule",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-SCORE",
        question_type="SHORT_RESPONSE",
        question="A player starts with score s and gains 6 bonus points. Write the new-score rule.",
        correct_answer="s + 6",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-SCORE",
            canonical_answer="s + 6",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        student_input="I do not know",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
    )
    hallucinated = GuidedEvaluation(
        student_state="STUCK",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE"],
        selected_error_code=None,
        confidence=0.9,
        next_objective=objective,
        tutor_message="What does the word 'falls' tell you about the operation?",
        tutor_message_voice="What does the word 'falls' tell you about the operation?",
    )

    aligned = classifier.align_guided_follow_up(hallucinated, request, rubric, objective)

    assert aligned.tutor_message == "That's okay. What general rule represents this situation?"
    assert aligned.tutor_message_voice == aligned.tutor_message


def test_guided_follow_up_preserves_a_relevant_non_revealing_llm_correction() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(concept_id="GENERAL_RULE", description="general rule", required=True)
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="counter-rule",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-006",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="A counter starts at any value c and increases by 4. Write the general rule.",
        correct_answer="c + 4",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-006",
            canonical_answer="c + 4",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        student_input="c - 4",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE"],
        selected_error_code="ERR-DIRECTION-REVERSED",
        confidence=0.9,
        next_objective=objective,
        tutor_message=(
            "It looks like you subtracted when you should have added. "
            "Which quantity can change in this situation?"
        ),
        tutor_message_voice=(
            "It looks like you subtracted when you should have added. "
            "Which quantity can change in this situation?"
        ),
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == evaluation.tutor_message
    assert aligned.tutor_message_voice == evaluation.tutor_message_voice


def test_guided_follow_up_replaces_an_answer_revealing_llm_reply() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(concept_id="GENERAL_RULE", description="general rule", required=True)
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="counter-rule",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-006",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="A counter starts at any value c and increases by 4. Write the general rule.",
        correct_answer="c + 4",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-006",
            canonical_answer="c + 4",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        student_input="c - 4",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE"],
        selected_error_code="ERR-DIRECTION-REVERSED",
        confidence=0.9,
        next_objective=objective,
        tutor_message="The correct rule is c plus 4.",
        tutor_message_voice="The correct rule is c plus 4.",
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == "Let's check that carefully. What general rule represents this situation?"
    assert aligned.tutor_message_voice == aligned.tutor_message


def test_guided_follow_up_blocks_unresolved_component_reveal() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-002",
        required_concepts=[
            GeneratedConcept(
                concept_id="CHANGING_VALUE",
                description="Identifies the changing quantity.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="FIXED_VALUE",
                description="Identifies the fixed value.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="OPERATION",
                description="Identifies the operation.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="components",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-002",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="In m + 7, identify the changing quantity, the fixed value and the operation.",
        correct_answer="m + 7",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-002",
            canonical_answer="m + 7",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        guided_teaching_state=GuidedTeachingState(
            question_id="Q-T01-002",
            objective_component_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
            confirmed_component_ids=[],
            missing_component_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
            active_component_id="CHANGING_VALUE",
            last_tutor_question_type="COMPONENT",
            selected_option_id=None,
            awaiting_response=True,
            active_step_id="CHANGING_VALUE",
        ),
        student_input="+7 is fixed",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["CHANGING_VALUE", "FIXED_VALUE", "OPERATION"],
        selected_error_code=None,
        confidence=0.9,
        next_objective=objective,
        tutor_message=(
            "You're on the right track. The fixed value is 7, while the changing "
            "quantity is m and the operation is addition. Does that help?"
        ),
        tutor_message_voice=(
            "You're on the right track. The fixed value is 7, while the changing "
            "quantity is m and the operation is addition. Does that help?"
        ),
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == "Good. Which part can take different possible values?"
    assert aligned.tutor_message_voice == aligned.tutor_message


def test_guided_follow_up_removes_unsupported_specific_praise() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="CHANGING_VALUE",
                description="Identifies what changes.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="FIXED_INCREMENT",
                description="Identifies what stays fixed.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="counter-components",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-006",
        question_type="MULTI_PART_SHORT_RESPONSE",
        question="A counter starts at any value c and increases by 4. Write the general rule and state what changes and what stays fixed.",
        correct_answer="c + 4",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-006",
            canonical_answer="c + 4",
            accepted_answers=[],
            verification_method="STRUCTURED_TEXT_MATCH",
            explanation_required=False,
        ),
        phase_2_prompt_context=_guided_context(0),
        student_input="c stays fixed",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=0,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE", "CHANGING_VALUE", "FIXED_INCREMENT"],
        selected_error_code=None,
        confidence=0.9,
        next_objective=objective,
        tutor_message=(
            "You mentioned that c stays fixed, which is correct! Now think about "
            "what happens when the counter increases by 4."
        ),
        tutor_message_voice=(
            "You mentioned that c stays fixed, which is correct! Now think about "
            "what happens when the counter increases by 4."
        ),
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == (
        "Now think about what happens when the counter increases by 4."
    )
    assert aligned.tutor_message_voice == aligned.tutor_message


def test_guided_follow_up_keeps_the_learner_selected_choice_explanation() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004",
        required_concepts=[
            GeneratedConcept(
                concept_id="ANSWER_SELECTION",
                description="Selects the correct option.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="ANSWER_EXPLANATION",
                description="Explains why the selected option works.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="choice-explanation",
        prompt_version="1.0.0",
    )
    objective = ActiveTeachingObjective(
        objective_type="EXPLAIN_REASONING",
        target_concept_ids=["ANSWER_EXPLANATION"],
        confirmed_concept_ids=["ANSWER_SELECTION"],
        missing_concept_ids=["ANSWER_EXPLANATION"],
    )
    request = ClassificationRequest(
        question_id="Q-T01-004",
        question_type="CHOICE_WITH_EXPLANATION",
        question="Which is the general rule? A: 12 + 4. B: n + 4. Explain briefly.",
        correct_answer="B",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-004",
            canonical_answer="B",
            accepted_answers=["B"],
            verification_method="EXACT_CHOICE_MATCH",
            explanation_required=True,
        ),
        phase_2_prompt_context=_guided_context(0),
        guided_teaching_state=GuidedTeachingState(
            question_id="Q-T01-004",
            objective_component_ids=["ANSWER_SELECTION", "ANSWER_EXPLANATION"],
            confirmed_component_ids=["ANSWER_SELECTION"],
            missing_component_ids=["ANSWER_EXPLANATION"],
            active_component_id="ANSWER_EXPLANATION",
            last_tutor_question_type="COMPONENT",
            selected_option_id="B",
            awaiting_response=True,
        ),
        student_input="option b",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=["ANSWER_SELECTION"],
        contradicted_concept_ids=[],
        missing_concept_ids=["ANSWER_EXPLANATION"],
        selected_error_code=None,
        confidence=0.9,
        next_objective=objective,
        tutor_message=(
            "You chose option B, which is a good start. Now explain why option B "
            "works as a general rule."
        ),
        tutor_message_voice=(
            "You chose option B, which is a good start. Now explain why option B "
            "works as a general rule."
        ),
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == evaluation.tutor_message
    assert aligned.tutor_message_voice == evaluation.tutor_message_voice


def test_guided_follow_up_blocks_an_unselected_choice_reveal() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004",
        required_concepts=[
            GeneratedConcept(
                concept_id="ANSWER_SELECTION",
                description="Selects the correct option.",
                required=True,
            )
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="choice-reveal",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    request = ClassificationRequest(
        question_id="Q-T01-004",
        question_type="CHOICE_WITH_EXPLANATION",
        question="Which is the general rule? A: 12 + 4. B: n + 4. Explain briefly.",
        correct_answer="B",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-004",
            canonical_answer="B",
            accepted_answers=["B"],
            verification_method="EXACT_CHOICE_MATCH",
            explanation_required=True,
        ),
        phase_2_prompt_context=_guided_context(0),
        guided_teaching_state=GuidedTeachingState(
            question_id="Q-T01-004",
            objective_component_ids=["ANSWER_SELECTION"],
            confirmed_component_ids=[],
            missing_component_ids=["ANSWER_SELECTION"],
            active_component_id="ANSWER_SELECTION",
            last_tutor_question_type="COMPONENT",
            selected_option_id="A",
            awaiting_response=True,
        ),
        student_input="option a",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    evaluation = GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["ANSWER_SELECTION"],
        selected_error_code=None,
        confidence=0.9,
        next_objective=objective,
        tutor_message="The correct choice is option B.",
        tutor_message_voice="The correct choice is option B.",
    )

    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == "Let's check that carefully. Which option do you choose?"


def test_guided_choice_repetition_keeps_the_llm_explanation_and_updates_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class _GuidedClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            nonlocal calls
            calls += 1
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["ANSWER_SELECTION"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["ANSWER_EXPLANATION"],
                selected_error_code=None,
                confidence=0.9,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_REASONING",
                    target_concept_ids=["ANSWER_EXPLANATION"],
                    confirmed_concept_ids=["ANSWER_SELECTION"],
                    missing_concept_ids=["ANSWER_EXPLANATION"],
                ),
                tutor_message=(
                    "You chose option B, which is a good start. Now explain why "
                    "option B works as a general rule."
                ),
                tutor_message_voice=(
                    "You chose option B, which is a good start. Now explain why "
                    "option B works as a general rule."
                ),
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T01-004",
            question_type="CHOICE_WITH_EXPLANATION",
            question=(
                "Which is the general rule: A) 12 + 4 or B) n + 4? "
                "Explain briefly."
            ),
            correct_answer="B",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-T01-004",
                canonical_answer="B",
                accepted_answers=["B", "n+4", "second option"],
                verification_method="CHOICE_AND_CONCEPT_MATCH",
                explanation_required=True,
            ),
            phase_2_prompt_context=_guided_context(0),
            guided_teaching_state=GuidedTeachingState(
                question_id="Q-T01-004",
                objective_component_ids=["ANSWER_SELECTION", "ANSWER_EXPLANATION"],
                confirmed_component_ids=[],
                missing_component_ids=["ANSWER_SELECTION", "ANSWER_EXPLANATION"],
                active_component_id="ANSWER_SELECTION",
                last_tutor_question_type="OPTION_COMPARISON",
                selected_option_id="A",
                awaiting_response=True,
            ),
            student_input="option b",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert calls == 1
    assert response.tutor_message.startswith("You chose option B")
    assert response.answer_reveal_allowed is True
    assert response.guided_teaching_state is not None
    assert response.guided_teaching_state.selected_option_id == "B"


def test_final_partial_wording_is_replaced_when_it_is_generic() -> None:
    rubric = _guided_rubric()
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["EXPANDED_MEANING"],
        confirmed_concept_ids=["OPERATION"],
        missing_concept_ids=["EXPANDED_MEANING"],
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["OPERATION"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["EXPANDED_MEANING"],
        selected_error_code=None,
        confidence=0.95,
        next_objective=objective,
        tutor_message="You identified the wrong component.",
        tutor_message_voice="You identified the wrong component.",
    )

    request = ClassificationRequest(
        question_id="Q-T02-002",
        question_type="SHORT_RESPONSE",
        question="What does cd mean?",
        correct_answer="c multiplied by d",
        answer_spec=_answer_spec("c multiplied by d", ["c times d"], "CONCEPT_TEXT_MATCH"),
        phase_2_prompt_context=_guided_context(0),
        student_input="multiplication",
        current_phase="GUIDED_PRACTICE",
        input_source="TEXT",
        transcript_confidence=None,
        attempt_count=1,
        current_hint_level=None,
    )
    aligned = classifier.align_guided_follow_up(evaluation, request, rubric, objective)

    assert aligned.tutor_message == "Good. What do the letters represent when the expression is expanded?"
    assert aligned.tutor_message_voice == aligned.tutor_message


@pytest.mark.parametrize("student_input", ["NPlus5", "n plus 5", "The general rule is NPlus5"])
def test_compact_spoken_general_rule_is_symbolically_equivalent(
    student_input: str,
) -> None:
    assert classifier.is_symbolically_equivalent(student_input, ["n + 5"])


def test_short_reason_does_not_confirm_general_rule_selection() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE_SELECTION",
                description="Selects n + 4 as the general rule.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="selection-rubric",
        prompt_version="1.0.0",
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_SELECTION"],
        selected_error_code=None,
        confidence=0.95,
        next_objective=None,
        tutor_message="Which rule works?",
        tutor_message_voice="Which rule works?",
    )

    merged = classifier.merge_authored_component_evidence(
        evaluation,
        rubric,
        "because n changes",
    )

    assert merged.newly_confirmed_concept_ids == []


def test_short_reason_turn_becomes_partial_instead_of_repeating_a_wrong_prompt() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE_SELECTION",
                description="Selects n + 4 as the general rule.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="EXPLANATION_FOR_SELECTION",
                description="Explains why n + 4 works for every starting value.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="selection-reason-rubric",
        prompt_version="1.0.0",
    )
    evaluation = GuidedEvaluation(
        student_state="WRONG",
        newly_confirmed_concept_ids=[],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_SELECTION", "EXPLANATION_FOR_SELECTION"],
        selected_error_code=None,
        confidence=0.95,
        next_objective=None,
        tutor_message="Try again.",
        tutor_message_voice="Try again.",
    )

    merged = classifier.merge_authored_component_evidence(
        evaluation,
        rubric,
        "because n is a variable and can change",
    )

    assert merged.student_state == "PARTIAL"
    assert merged.newly_confirmed_concept_ids == ["EXPLANATION_FOR_SELECTION"]
    assert merged.missing_concept_ids == ["GENERAL_RULE_SELECTION"]


def test_compact_expression_component_gets_a_general_rule_prompt() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-001",
        required_concepts=[
            GeneratedConcept(
                concept_id="REQUIRED_COMPONENT_1",
                description="n + 5",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="expression-rubric",
        prompt_version="1.0.0",
    )
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["REQUIRED_COMPONENT_1"],
        confirmed_concept_ids=[],
        missing_concept_ids=["REQUIRED_COMPONENT_1"],
    )

    assert classifier.focused_unresolved_prompt(rubric, objective, "fallback") == (
        "What general rule represents this situation?"
    )


def test_wrong_choice_comparison_does_not_treat_yes_as_progress() -> None:
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["GENERAL_RULE_SELECTION"],
        confirmed_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_SELECTION"],
    )
    follow_up = classifier.option_comparison_follow_up(
        [
            ConversationMessage(
                role="assistant",
                content=(
                    "You chose that option. Compare it with the situation: can one "
                    "fixed starting number describe every possible case?"
                ),
            )
        ],
        "yes",
        objective,
        None,
    )

    assert follow_up is not None
    assert follow_up.student_state == "WRONG"
    assert "Not quite" in follow_up.tutor_message


def test_wrong_choice_comparison_accepts_a_negative_correction_without_completion() -> None:
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["GENERAL_RULE_SELECTION"],
        confirmed_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_SELECTION"],
    )
    follow_up = classifier.option_comparison_follow_up(
        [
            ConversationMessage(
                role="assistant",
                content=(
                    "You chose that option. Compare it with the situation: can one "
                    "fixed starting number describe every possible case?"
                ),
            )
        ],
        "it's false",
        objective,
        None,
    )

    assert follow_up is not None
    assert follow_up.student_state == "PARTIAL"
    assert "cannot describe every case" in follow_up.tutor_message


def test_choice_reaffirmation_keeps_the_existing_comparison_question() -> None:
    objective = ActiveTeachingObjective(
        objective_type="ANSWER_QUESTION",
        target_concept_ids=["GENERAL_RULE_SELECTION"],
        confirmed_concept_ids=[],
        missing_concept_ids=["GENERAL_RULE_SELECTION"],
    )
    state = GuidedTeachingState(
        question_id="Q-T01-004",
        objective_component_ids=["GENERAL_RULE_SELECTION"],
        confirmed_component_ids=[],
        missing_component_ids=["GENERAL_RULE_SELECTION"],
        active_component_id="GENERAL_RULE_SELECTION",
        last_tutor_question_type="OPTION_COMPARISON",
        selected_option_id="A",
        awaiting_response=True,
    )

    follow_up = classifier.option_comparison_follow_up([], "I choose option A", objective, state)

    assert follow_up is not None
    assert follow_up.student_state == "PARTIAL"
    assert "already chosen" in follow_up.tutor_message
    assert "can one fixed starting number" in follow_up.tutor_message


def test_copied_numeric_example_is_repaired_before_the_general_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoEvaluationClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            raise AssertionError("copied source data must be repaired before LLM evaluation")

    rubric = GeneratedQuestionRubric(
        question_id="CT-T01-P3",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule.",
                required=True,
            )
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="copied-example",
        prompt_version="1.0.0",
    )
    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _NoEvaluationClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question_id="CT-T01-P3",
            question_type="SHORT_RESPONSE",
            question="3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.",
            correct_answer="n + 5",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-CT-T01-P3",
                canonical_answer="n + 5",
                accepted_answers=[],
                verification_method="STRUCTURED_TEXT_MATCH",
                explanation_required=False,
            ),
            phase_2_prompt_context=_guided_context(0),
            generated_question_rubric=rubric,
            active_teaching_objective=classifier.initial_guided_objective(rubric),
            student_input="3 + 5, 9 + 5, 14 + 4, so the added number changes",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "WRONG"
    assert "14 + 5, not 14 + 4" in response.tutor_message
    assert response.guided_teaching_state is not None
    assert response.guided_teaching_state.last_tutor_question_type == "SOURCE_CORRECTION"


def test_changing_starting_numbers_are_acknowledged_before_requesting_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoEvaluationClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            raise AssertionError("the active teaching-step response is deterministic")

    rubric = GeneratedQuestionRubric(
        question_id="CT-T01-P3",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule.",
                required=True,
            )
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="changing-starting-numbers",
        prompt_version="1.0.0",
    )
    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _NoEvaluationClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question_id="CT-T01-P3",
            question_type="SHORT_RESPONSE",
            question=(
                "3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number. "
                "Write the general rule."
            ),
            correct_answer="n + 5",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-CT-T01-P3",
                canonical_answer="n + 5",
                accepted_answers=[],
                verification_method="STRUCTURED_TEXT_MATCH",
                explanation_required=False,
            ),
            phase_2_prompt_context=_guided_context(0),
            generated_question_rubric=rubric,
            active_teaching_objective=classifier.initial_guided_objective(rubric),
            student_input="the first numbers, starting numbers change",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "PARTIAL"
    assert response.tutor_message == (
        "Yes—the starting number changes. Replace it with a letter and keep "
        "the operation that stays the same."
    )


def test_source_correction_keeps_the_same_active_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoEvaluationClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            raise AssertionError("the explicit source correction has a deterministic response")

    rubric = GeneratedQuestionRubric(
        question_id="CT-T01-P3",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE",
                description="States the general rule.",
                required=True,
            )
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="source-follow-up",
        prompt_version="1.0.0",
    )
    objective = classifier.initial_guided_objective(rubric)
    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _NoEvaluationClient(),
    )

    response = classify_student_response(
        ClassificationRequest(
            question_id="CT-T01-P3",
            question_type="SHORT_RESPONSE",
            question="3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.",
            correct_answer="n + 5",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-CT-T01-P3",
                canonical_answer="n + 5",
                accepted_answers=[],
                verification_method="STRUCTURED_TEXT_MATCH",
                explanation_required=False,
            ),
            phase_2_prompt_context=_guided_context(0),
            generated_question_rubric=rubric,
            active_teaching_objective=objective,
            guided_teaching_state=GuidedTeachingState(
                question_id="CT-T01-P3",
                objective_component_ids=["GENERAL_RULE"],
                confirmed_component_ids=[],
                missing_component_ids=["GENERAL_RULE"],
                active_component_id="GENERAL_RULE",
                last_tutor_question_type="SOURCE_CORRECTION",
                selected_option_id=None,
                awaiting_response=True,
            ),
            student_input="5",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "PARTIAL"
    assert "What general rule represents this situation?" in response.tutor_message
    assert response.guided_teaching_state is not None
    assert response.guided_teaching_state.active_component_id == "GENERAL_RULE"


def test_reversed_fixed_component_is_not_praised_as_correct() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-006",
        required_concepts=[
            GeneratedConcept(
                concept_id="CHANGING_VALUE",
                description="c changes",
                required=True,
            ),
            GeneratedConcept(
                concept_id="FIXED_INCREMENT",
                description="+4 stays fixed",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="counter-rubric",
        prompt_version="1.0.0",
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["CHANGING_VALUE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["FIXED_INCREMENT"],
        selected_error_code=None,
        confidence=0.95,
        next_objective=None,
        tutor_message="Good.",
        tutor_message_voice="Good.",
    )

    merged = classifier.merge_authored_component_evidence(
        evaluation,
        rubric,
        "+4 changes",
    )

    assert merged.student_state == "WRONG"
    assert merged.newly_confirmed_concept_ids == []
    assert merged.contradicted_concept_ids == ["FIXED_INCREMENT"]


def test_contradicted_role_cannot_enter_persistent_component_evidence() -> None:
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["FIXED_VALUE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["CHANGING_VALUE", "OPERATION"],
        selected_error_code=None,
        confidence=0.96,
        next_objective=None,
        tutor_message="Good.",
        tutor_message_voice="Good.",
    )

    verified = classifier.apply_focused_component_evidence(
        evaluation,
        FocusedComponentEvidence(
            component_id="FIXED_VALUE",
            status="CONTRADICTED",
            evidence="the fixed value is m",
            confidence=0.99,
        ),
        0.85,
    )

    assert verified.newly_confirmed_concept_ids == []
    assert verified.contradicted_concept_ids == ["FIXED_VALUE"]


def test_component_claim_requires_positive_adjudication() -> None:
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["FIXED_VALUE"],
        preserved_concept_ids=[],
        contradicted_concept_ids=[],
        missing_concept_ids=["CHANGING_VALUE", "OPERATION"],
        selected_error_code=None,
        confidence=0.96,
        next_objective=None,
        tutor_message="Good.",
        tutor_message_voice="Good.",
    )

    verified = classifier.apply_focused_component_evidence(
        evaluation,
        FocusedComponentEvidence(
            component_id="FIXED_VALUE",
            status="NOT_DEMONSTRATED",
            evidence="The learner did not state the fixed value.",
            confidence=0.5,
        ),
        0.85,
    )

    assert verified.newly_confirmed_concept_ids == []
    assert verified.contradicted_concept_ids == []


def _multipart_guided_rubric() -> GeneratedQuestionRubric:
    return GeneratedQuestionRubric(
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


def _explain_again_request() -> ExplainAgainRequest:
    return ExplainAgainRequest(
        question_id="Q-T01-006",
        question="A counter starts at c and increases by 4. State the general rule and explain what changes and stays fixed.",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-T01-006",
            canonical_answer="c + 4; c changes; add 4 stays fixed",
            accepted_answers=["c + 4"],
            verification_method="STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
            explanation_required=True,
        ),
        generated_question_rubric=_multipart_guided_rubric(),
        active_teaching_objective=ActiveTeachingObjective(
            objective_type="EXPLAIN_CONCEPT",
            target_concept_ids=["CHANGING_VALUE", "FIXED_INCREMENT"],
            confirmed_concept_ids=["GENERAL_RULE"],
            missing_concept_ids=["CHANGING_VALUE", "FIXED_INCREMENT"],
        ),
        first_unresolved_concept_id="CHANGING_VALUE",
        guided_student_state="PARTIAL",
        selected_error_code="ERR-T01-COUNTER-RULE",
        recorded_misconception=RecordedMisconception(
            error_code="ERR-T01-COUNTER-RULE",
            description="Treats c as fixed rather than a starting value.",
        ),
        recent_conversation=[
            ConversationMessage(role="user", content="The rule is c + 4."),
            ConversationMessage(role="assistant", content="What can c represent?"),
        ],
        active_support_level="SCAFFOLD",
        highest_support_used="SCAFFOLD",
        visible_visual_cue=VisibleVisualCue(
            show=True,
            cue_id="VC-T01-COUNTER-CHANGE",
            cue_type="CONCEPT_CARD",
            description="A counter can start at different values.",
            actions=[],
        ),
        active_scaffold=ActiveScaffoldState(
            scaffold_id="SCF-T01-COUNTER-RULE",
            current_step_id="SCF-T01-CTR-S1",
            step_number=1,
            total_steps=4,
            step_text="Which quantity can change?",
            step_voice="Which quantity can change?",
        ),
        answer_reveal_allowed=False,
    )


def test_explain_again_reexpresses_the_unresolved_component_without_progression_change(
    monkeypatch,
) -> None:
    captured_requests: list[ExplainAgainRequest] = []

    class _ExplainAgainClient:
        def generate_explain_again_message(
            self,
            request: ExplainAgainRequest,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            captured_requests.append(request)
            messages = [
                "Look at the counter card: c is the starting value, so what could make it different each time?",
                "Use the first scaffold question again: how could the counter begin at one value today and another tomorrow?",
            ]
            message = messages[len(captured_requests) - 1]
            return OpenAIExplainAgainMessage(
                tutor_message=message,
                tutor_message_voice_optimised=message,
                answer_reveal_risk=False,
                confidence=0.96,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ExplainAgainClient(),
    )

    first = classifier.generate_explain_again_response(_explain_again_request())
    second = classifier.generate_explain_again_response(_explain_again_request())

    assert len(captured_requests) == 2
    assert captured_requests[0].generated_question_rubric.required_concepts[1].concept_id == "CHANGING_VALUE"
    assert captured_requests[0].active_scaffold is not None
    assert captured_requests[0].visible_visual_cue is not None
    assert first.tutor_message != second.tutor_message
    assert first.attempt_increment == 0
    assert first.progression_change_requested is False
    assert first.support_served_this_turn is None
    assert first.guided_student_state == "PARTIAL"
    assert first.active_teaching_objective.confirmed_concept_ids == ["GENERAL_RULE"]
    assert first.first_unresolved_concept_id == "CHANGING_VALUE"
    assert first.active_support_level == "SCAFFOLD"
    assert first.highest_support_used == "SCAFFOLD"
    assert first.active_scaffold is not None


def test_explain_again_retries_a_revealing_llm_response_without_canned_wording(
    monkeypatch,
) -> None:
    validation_feedback: list[str | None] = []

    class _ExplainAgainClient:
        def generate_explain_again_message(
            self,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            validation_feedback.append(cast(str | None, kwargs["validation_feedback"]))
            if len(validation_feedback) == 1:
                return OpenAIExplainAgainMessage(
                    tutor_message="A counter can begin with any c and always moves on by four.",
                    tutor_message_voice_optimised="A counter can begin with any c and always moves on by four.",
                    answer_reveal_risk=True,
                    confidence=0.99,
                )
            return OpenAIExplainAgainMessage(
                tutor_message="Think about the starting value: could it be the same every time?",
                tutor_message_voice_optimised="Think about the starting value: could it be the same every time?",
                answer_reveal_risk=False,
                confidence=0.98,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ExplainAgainClient(),
    )

    response = classifier.generate_explain_again_response(_explain_again_request())

    assert len(validation_feedback) == 2
    assert validation_feedback[0] is None
    assert validation_feedback[1] is not None
    assert "exactly one Socratic question" in validation_feedback[1]
    assert response.tutor_message == (
        "Think about the starting value: could it be the same every time?"
    )
    assert response.attempt_increment == 0
    assert response.progression_change_requested is False


def test_explain_again_guardrail_retry_removes_answer_bearing_context() -> None:
    request = _explain_again_request()
    payload = openai_client.build_explain_again_guardrail_retry_payload(
        request,
        "Return exactly one Socratic question.",
        "1.0.1",
    )

    assert payload["guardrail_retry_mode"] == "SOCRATIC_QUESTION_ONLY"
    assert payload["first_unresolved_concept_id"] == "CHANGING_VALUE"
    assert payload["answer_reveal_allowed"] is False
    assert "answer_spec" not in payload
    assert "required_components" not in payload
    assert "active_teaching_objective" not in payload
    assert "recent_conversation" not in payload
    assert "recorded_misconception" not in payload
    visible_visual_cue = payload["visible_visual_cue"]
    assert isinstance(visible_visual_cue, dict)
    assert "description" not in visible_visual_cue


def test_explain_again_uses_safe_state_aware_response_when_all_llm_wording_reveals_answer(
    monkeypatch,
) -> None:
    calls = 0

    class _AlwaysRevealingExplainAgainClient:
        def generate_explain_again_message(
            self,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            nonlocal calls
            calls += 1
            return OpenAIExplainAgainMessage(
                tutor_message="The complete answer is c plus four, c changes, and four stays fixed.",
                tutor_message_voice_optimised="The complete answer is c plus four, c changes, and four stays fixed.",
                answer_reveal_risk=True,
                confidence=0.99,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _AlwaysRevealingExplainAgainClient(),
    )

    request = _explain_again_request()
    response = classifier.generate_explain_again_response(request)

    rules = classifier.load_classifier_rules()
    assert calls == rules.guided_learning.maximum_retries + 1
    assert response.tutor_message == (
        "Let’s look at the step already on your screen in a different way. "
        "What do you notice first?"
    )
    assert response.attempt_increment == 0
    assert response.active_teaching_objective == request.active_teaching_objective
    assert response.active_support_level == request.active_support_level
    assert response.progression_change_requested is False


@pytest.mark.parametrize(
    ("request_update", "expected_message"),
    [
        (
            {
                "first_unresolved_concept_id": "FIXED_INCREMENT",
            },
            "out of runtime rubric order",
        ),
        (
            {
                "active_teaching_objective": ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["CHANGING_VALUE"],
                    confirmed_concept_ids=["GENERAL_RULE"],
                    missing_concept_ids=["CHANGING_VALUE"],
                )
            },
            "omits runtime required components",
        ),
        (
            {
                "active_teaching_objective": ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["CHANGING_VALUE", "FIXED_INCREMENT"],
                    confirmed_concept_ids=["GENERAL_RULE", "CHANGING_VALUE"],
                    missing_concept_ids=["CHANGING_VALUE", "FIXED_INCREMENT"],
                )
            },
            "overlaps confirmed and missing",
        ),
        (
            {
                "selected_error_code": None,
            },
            "must both be present or absent",
        ),
        (
            {
                "recorded_misconception": None,
            },
            "must both be present or absent",
        ),
        (
            {
                "recorded_misconception": RecordedMisconception(
                    error_code="ERR-OTHER",
                    description="A different recorded misconception.",
                ),
            },
            "does not match selected error",
        ),
        (
            {
                "active_support_level": "SCAFFOLD",
                "highest_support_used": "HINT",
            },
            "active support exceeds highest support",
        ),
        (
            {
                "active_scaffold": ActiveScaffoldState(
                    scaffold_id="SCF-T01-COUNTER-RULE",
                    current_step_id="SCF-T01-CTR-S4",
                    step_number=5,
                    total_steps=4,
                    step_text="Which quantity can change?",
                    step_voice="Which quantity can change?",
                )
            },
            "scaffold step exceeds total steps",
        ),
    ],
)
def test_explain_again_rejects_invalid_persisted_state_contract(
    request_update: dict[str, object],
    expected_message: str,
) -> None:
    request = _explain_again_request().model_copy(update=request_update)

    with pytest.raises(AdapterError, match=expected_message):
        classifier.validate_explain_again_request(request)


def test_explain_again_rejects_duplicate_runtime_component_contract() -> None:
    required_components = [
        GeneratedConcept(
            concept_id="GENERAL_RULE",
            required=True,
            description="States the general rule.",
        ),
        GeneratedConcept(
            concept_id="GENERAL_RULE",
            required=True,
            description="Explains the changing value.",
        ),
    ]
    request = _explain_again_request().model_copy(
        update={
            "generated_question_rubric": _explain_again_request().generated_question_rubric.model_copy(
                update={"required_concepts": required_components}
            )
        }
    )

    with pytest.raises(AdapterError, match="unique runtime component IDs"):
        classifier.validate_explain_again_request(request)


def test_explain_again_rejects_optional_component_in_active_objective() -> None:
    request = _explain_again_request()
    components = [
        component.model_copy(update={"required": False})
        if component.concept_id == "FIXED_INCREMENT"
        else component
        for component in request.generated_question_rubric.required_concepts
    ]
    invalid = request.model_copy(
        update={
            "generated_question_rubric": request.generated_question_rubric.model_copy(
                update={"required_concepts": components}
            )
        }
    )

    with pytest.raises(AdapterError, match="unknown runtime component IDs"):
        classifier.validate_explain_again_request(invalid)


def test_explain_again_limits_typed_conversation_history(monkeypatch) -> None:
    captured_history: list[ConversationMessage] = []

    class _ExplainAgainClient:
        def generate_explain_again_message(
            self,
            request: ExplainAgainRequest,
            **kwargs: object,
        ) -> OpenAIExplainAgainMessage:
            captured_history.extend(request.recent_conversation)
            return OpenAIExplainAgainMessage(
                tutor_message="Could the counter start at the same value every time?",
                tutor_message_voice_optimised="Could the counter start at the same value every time?",
                answer_reveal_risk=False,
                confidence=0.96,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _ExplainAgainClient(),
    )
    request = _explain_again_request().model_copy(
        update={
            "recent_conversation": [
                ConversationMessage(role="user", content=f"turn {index}")
                for index in range(8)
            ]
        }
    )

    classifier.generate_explain_again_response(request)

    assert len(captured_history) == classifier.load_classifier_rules().guided_learning.maximum_recent_history_turns
    assert captured_history[0].content == "turn 2"


def test_explain_again_requires_an_enabled_llm_client() -> None:
    with pytest.raises(AdapterError, match="Explain Again requires an enabled OpenAI"):
        classifier.generate_explain_again_response(_explain_again_request())


def test_guided_evaluation_schema_rejects_blank_tutor_messages() -> None:
    payload = {
        "student_state": "WRONG",
        "newly_confirmed_concept_ids": [],
        "preserved_concept_ids": [],
        "contradicted_concept_ids": [],
        "missing_concept_ids": ["OPERATION", "EXPANDED_MEANING"],
        "selected_error_code": "ERR-T02-ADDITION",
        "confidence": 0.95,
        "next_objective": None,
        "tutor_message": "",
        "tutor_message_voice": "",
    }

    with pytest.raises(ValueError):
        GuidedEvaluation.model_validate(payload)

    schema = GuidedEvaluation.model_json_schema()
    assert schema["properties"]["tutor_message"]["minLength"] == 1
    assert schema["properties"]["tutor_message_voice"]["minLength"] == 1


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


def test_ai_engine_does_not_review_canvas_for_answer_request_with_evidence() -> None:
    """Production shape: /canvas/submit always sets has_canvas_evidence=True.

    The fixture-shaped test above passed even while the guard was dead code,
    because has_canvas_evidence short-circuited it. Grounded tokens are supplied
    here so a correction would genuinely be drawable if the guard were missing.
    """

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
            has_canvas_evidence=True,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 - 5", 0.95),
            ],
            spatial_tokens=[
                SpatialMathToken(
                    token_id=f"step-2:token-{index}",
                    step_id="step-2",
                    text=text,
                    bounding_box={"x": 0.1 * index, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                )
                for index, text in enumerate(["x", "=", "9", "-", "5"], start=1)
            ],
        )
    )

    assert response.intent == "REQUESTING_ANSWER"
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


def test_canvas_math_review_emits_grounded_tokens_for_correctable_error() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question="x + 4 = 9",
            correct_answer="x = 5",
            student_input="x + 4 = 9\nx = 9 - 5",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            canvas_regions=[
                _canvas_region("step-1", "x + 4 = 9", 0.95),
                _canvas_region("step-2", "x = 9 - 5", 0.95),
            ],
            spatial_tokens=[
                SpatialMathToken(
                    token_id="step-2:token-1",
                    step_id="step-2",
                    text="x",
                    bounding_box={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-2:token-2",
                    step_id="step-2",
                    text="=",
                    bounding_box={"x": 0.2, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-2:token-3",
                    step_id="step-2",
                    text="9",
                    bounding_box={"x": 0.3, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-2:token-4",
                    step_id="step-2",
                    text="-",
                    bounding_box={"x": 0.4, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-2:token-5",
                    step_id="step-2",
                    text="5",
                    bounding_box={"x": 0.5, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.target_token_ids == ["step-2:token-5"]
    assert response.mistake_classification.error_token == "5"
    assert response.mistake_classification.expected_token == "4"


def test_canvas_math_review_writes_grounded_direct_expression_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GuidedClient:
        def evaluate_guided_turn(self, **kwargs: object) -> GuidedEvaluation:
            objective = cast(ActiveTeachingObjective, kwargs["active_objective"])
            return GuidedEvaluation(
                student_state="WRONG",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=objective.missing_concept_ids,
                selected_error_code=None,
                confidence=0.95,
                next_objective=objective,
                tutor_message="Check the fixed amount in your rule.",
                tutor_message_voice="Check the fixed amount in your rule.",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: GuidedClient(),
    )
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-001",
        required_concepts=[
            GeneratedConcept(
                concept_id="CONCEPT_GENERAL_RULE",
                description="The general rule is n + 5.",
                required=True,
            )
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="direct-expression",
        prompt_version="1.0.0",
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T01-001",
            question_type="SHORT_RESPONSE",
            question=(
                "3 + 5, 9 + 5, 14 + 5. Use n for the changing starting "
                "number. Write the general rule."
            ),
            correct_answer="n+5",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-T01-001",
                canonical_answer="n+5",
                accepted_answers=[],
                verification_method="STRUCTURED_TEXT_MATCH",
                explanation_required=False,
            ),
            phase_2_prompt_context=_guided_context(0),
            generated_question_rubric=rubric,
            student_input="n+b",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            has_canvas_evidence=True,
            canvas_regions=[_canvas_region("step-1", "n+b", 1.0)],
            spatial_tokens=[
                SpatialMathToken(
                    token_id="step-1:token-1",
                    step_id="step-1",
                    text="n",
                    bounding_box={"x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-1:token-2",
                    step_id="step-1",
                    text="+",
                    bounding_box={"x": 0.2, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
                SpatialMathToken(
                    token_id="step-1:token-3",
                    step_id="step-1",
                    text="b",
                    bounding_box={"x": 0.3, "y": 0.1, "width": 0.1, "height": 0.1},
                    alignment_confidence=0.95,
                ),
            ],
        )
    )

    assert response.mistake_classification is not None
    assert response.mistake_classification.status == "mistake_found"
    assert response.mistake_classification.target_token_ids == ["step-1:token-3"]
    assert response.mistake_classification.error_token == "b"
    assert response.mistake_classification.expected_token == "5"
    assert [intent.kind for intent in response.annotation_intents] == [
        "circle_target",
        "write_correction",
        "draw_arrow",
    ]
    assert response.annotation_intents[1].text == "5"


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


def test_phase3_choice_submission_returns_terminal_independent_outcome() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-IP-1",
            question_type="SINGLE_CHOICE",
            question="Choose A.",
            correct_answer="A",
            answer_spec=AnswerSpec(
                answer_spec_id="AS-IP-1",
                canonical_answer="A",
                accepted_answers=[],
                verification_method="EXACT_CHOICE_MATCH",
            ),
            student_input="A",
            current_phase="INDEPENDENT_PRACTICE",
            input_source="CHOICE",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
            phase3_submission_confirmed=True,
            phase3_submission_kind="CHOICE",
        )
    )

    assert response.independent_outcome == "INDEPENDENTLY_VERIFIED"
    assert response.attempt_increment == 1
    assert response.independent_attempt_terminal is True
    assert response.visual_cue.show is False
    assert response.annotation_intents == []


def test_phase3_non_submission_does_not_mutate_independent_progression() -> None:
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-IP-1",
            question_type="SHORT_RESPONSE",
            question="Write an expression.",
            correct_answer="t - 3",
            student_input="Can you help?",
            current_phase="INDEPENDENT_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=0,
            current_hint_level=None,
            phase3_submission_confirmed=False,
            phase3_submission_kind=None,
        )
    )

    assert response.independent_outcome == "AWAITING_SUBMISSION"
    assert response.attempt_increment == 0
    assert response.independent_attempt_terminal is False
    assert response.student_model_events == []


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

    assert guarded.tutor_message == result.tutor_message
    assert guarded.tutor_message_voice == result.tutor_message_voice


def test_canvas_wording_retries_an_answer_revealing_draft() -> None:
    captured_feedback: list[str | None] = []

    class _CanvasWordingClient:
        def build_tutor_message(
            self,
            **kwargs: object,
        ) -> openai_client.OpenAITutorMessage:
            captured_feedback.append(
                cast(str | None, kwargs["validation_feedback"])
            )
            if len(captured_feedback) == 1:
                return openai_client.OpenAITutorMessage(
                    tutor_message="The answer is x = 5.",
                    tutor_message_voice_optimised="The answer is x equals 5.",
                    confidence=0.95,
                )
            return openai_client.OpenAITutorMessage(
                tutor_message="Which operation would undo adding four?",
                tutor_message_voice_optimised="Which operation would undo adding four?",
                confidence=0.95,
            )

    message = classifier.build_tutor_message_with_openai(
        request=ClassificationRequest(
            question_id="Q-CANVAS",
            question="Solve x + 4 = 9.",
            correct_answer="x = 5",
            student_input="x = 6",
            current_phase="GUIDED_PRACTICE",
            input_source="CANVAS",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        ),
        rules=classifier.load_classifier_rules(),
        intent="SUBMITTING_ANSWER",
        evaluation="INCORRECT",
        error_type="ARITHMETIC_ERROR",
        response_strategy="GUIDED_HINT",
        hint_level=1,
        canvas_context={"incorrect_step": "x = 6"},
        openai_client=_CanvasWordingClient(),
    )

    assert message is not None
    assert message.tutor_message == "Which operation would undo adding four?"
    assert captured_feedback[0] is None
    assert captured_feedback[1] is not None


def test_support_aware_wording_receives_visible_visual_cue() -> None:
    captured_support_context: list[dict[str, object] | None] = []

    class _SupportAwareClient:
        def build_tutor_message(
            self,
            **kwargs: object,
        ) -> openai_client.OpenAITutorMessage:
            captured_support_context.append(
                cast(dict[str, object] | None, kwargs["support_context"])
            )
            return openai_client.OpenAITutorMessage(
                tutor_message=(
                    "Look at the visual cue on your screen. It shows that the "
                    "starting value can change. Which part can vary?"
                ),
                tutor_message_voice_optimised=(
                    "Look at the visual cue on your screen. It shows that the "
                    "starting value can change. Which part can vary?"
                ),
                confidence=0.95,
            )

    support_context = {
        "support_type": "VISUAL_CUE",
        "visual_cue": {
            "show": True,
            "cue_id": "VC-T01-CHANGE",
            "cue_type": None,
            "description": "The starting value changes while the operation stays fixed.",
            "actions": [],
        },
        "instruction": "Explain the visible cue and ask one focused next question.",
    }

    message = classifier.build_support_aware_tutor_message(
        question_id="Q-T01-006",
        question="A counter starts at any value c and increases by 4.",
        correct_answer="c + 4",
        student_input="c - 4",
        evaluation="INCORRECT",
        error_type="SIGN_ERROR",
        response_strategy="PROVIDE_VISUAL_CUE",
        hint_level=None,
        conversation_history=[],
        support_context=support_context,
        openai_client=_SupportAwareClient(),
    )

    assert message is not None
    assert message.tutor_message.startswith("Look at the visual cue")
    assert captured_support_context == [support_context]


def test_guided_evaluator_retries_answer_revealing_wording(monkeypatch) -> None:
    feedback: list[str | None] = []

    class _GuidedClient:
        def generate_guided_rubric(
            self,
            **kwargs: object,
        ) -> GeneratedQuestionRubric:
            return _guided_rubric()

        def evaluate_guided_turn(
            self,
            **kwargs: object,
        ) -> GuidedEvaluation:
            feedback.append(cast(str | None, kwargs["validation_feedback"]))
            message = (
                "The answer is c multiplied by d."
                if len(feedback) == 1
                else "You identified multiplication. What do the two letters represent?"
            )
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
                    confirmed_concept_ids=["OPERATION"],
                    missing_concept_ids=["EXPANDED_MEANING"],
                ),
                tutor_message=message,
                tutor_message_voice=message,
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
    assert response.tutor_message == (
        "You identified multiplication. What do the two letters represent?"
    )
    assert feedback[0] is None
    assert feedback[1] is not None


def test_guided_answer_reveal_fallback_names_the_missing_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_calls = 0

    class _GuidedClient:
        def generate_guided_rubric(
            self,
            **kwargs: object,
        ) -> GeneratedQuestionRubric:
            del kwargs
            return GeneratedQuestionRubric(
                question_id="Q-EXPLAIN-RULE",
                required_concepts=[
                    GeneratedConcept(
                        concept_id="GENERAL_RULE",
                        description="States the general rule.",
                        required=True,
                    ),
                    GeneratedConcept(
                        concept_id="EXPLANATION_OF_RULE",
                        description="Explains why the general rule represents the situation.",
                        required=True,
                    ),
                ],
                completion_rule="ALL_REQUIRED_CONCEPTS",
                cache_key="explanation-rubric",
                prompt_version="1.0.0",
            )

        def evaluate_guided_turn(
            self,
            **kwargs: object,
        ) -> GuidedEvaluation:
            nonlocal evaluation_calls
            del kwargs
            evaluation_calls += 1
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["GENERAL_RULE"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["EXPLANATION_OF_RULE"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_REASONING",
                    target_concept_ids=["EXPLANATION_OF_RULE"],
                    confirmed_concept_ids=["GENERAL_RULE"],
                    missing_concept_ids=["EXPLANATION_OF_RULE"],
                ),
                tutor_message="The complete answer is n plus four because four is added.",
                tutor_message_voice="The complete answer is n plus four because four is added.",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-EXPLAIN-RULE",
            question="Write the general rule and explain why it represents the situation.",
            correct_answer="n plus four because four is added",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-EXPLAIN-RULE",
                canonical_answer="n plus four because four is added",
                accepted_answers=["n + 4"],
                verification_method="STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
                explanation_required=True,
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="n + 4",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert evaluation_calls > 1
    assert response.guided_student_state == "PARTIAL"
    assert response.tutor_message == (
        "You have given the answer. Now explain why it is true in this situation."
    )
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.missing_concept_ids == [
        "EXPLANATION_OF_RULE"
    ]


@pytest.mark.parametrize(
    "student_input",
    [
        "because n is a variable",
        "because we can add 4 to anynumber n",
        "n can represent any number",
    ],
)
def test_guided_general_rule_explanation_accepts_clear_paraphrases(
    monkeypatch: pytest.MonkeyPatch,
    student_input: str,
) -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-T01-004",
        required_concepts=[
            GeneratedConcept(
                concept_id="GENERAL_RULE_SELECTION",
                description="Selects n + 4 as the general rule.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="EXPLANATION_FOR_SELECTION",
                description=(
                    "Explains why n + 4 is a general rule rather than a "
                    "specific numerical case."
                ),
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="general-rule-choice-rubric",
        prompt_version="1.0.0",
    )

    class _GuidedClient:
        def evaluate_guided_turn(
            self,
            **kwargs: object,
        ) -> GuidedEvaluation:
            del kwargs
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=["GENERAL_RULE_SELECTION"],
                contradicted_concept_ids=[],
                missing_concept_ids=["EXPLANATION_FOR_SELECTION"],
                selected_error_code=None,
                confidence=0.9,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_REASONING",
                    target_concept_ids=["EXPLANATION_FOR_SELECTION"],
                    confirmed_concept_ids=["GENERAL_RULE_SELECTION"],
                    missing_concept_ids=["EXPLANATION_FOR_SELECTION"],
                ),
                tutor_message="Please provide a more complete explanation.",
                tutor_message_voice="Please provide a more complete explanation.",
            )

        def adjudicate_component_evidence(
            self,
            **kwargs: object,
        ) -> FocusedComponentEvidence:
            target_component = kwargs["target_component"]
            assert isinstance(target_component, GeneratedConcept)
            return FocusedComponentEvidence(
                component_id=target_component.concept_id,
                status="DEMONSTRATED",
                evidence=student_input,
                confidence=0.96,
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T01-004",
            question=(
                "Which is the general rule: A) 12 + 4 or B) n + 4? "
                "Explain briefly."
            ),
            question_type="CHOICE_WITH_EXPLANATION",
            correct_answer="B",
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-T01-004",
                canonical_answer="B",
                accepted_answers=["B", "n + 4"],
                verification_method="CHOICE_AND_CONCEPT_MATCH",
                explanation_required=True,
            ),
            generated_question_rubric=rubric,
            active_teaching_objective=ActiveTeachingObjective(
                objective_type="EXPLAIN_REASONING",
                target_concept_ids=["EXPLANATION_FOR_SELECTION"],
                confirmed_concept_ids=["GENERAL_RULE_SELECTION"],
                missing_concept_ids=["EXPLANATION_FOR_SELECTION"],
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input=student_input,
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=2,
            current_hint_level=1,
        )
    )

    assert response.guided_student_state == "CORRECT"
    assert response.question_completed is True
    assert response.active_teaching_objective is None


def test_multipart_answer_numbers_do_not_trigger_numeric_reveal_guardrail() -> None:
    rules = classifier.load_classifier_rules()
    canonical_answer = "4 × n; p × q; r × r; c ÷ d; 2 × (x + 1)"

    assert classifier.contains_answer_reveal(
        "You identified r times r. What does the bracket represent?",
        canonical_answer,
        rules,
    ) is False
    assert classifier.contains_answer_reveal(
        "The answer is 4 × n; p × q; r × r; c ÷ d; 2 × (x + 1).",
        canonical_answer,
        rules,
    ) is True


def test_single_numeric_answer_still_uses_numeric_reveal_guardrail() -> None:
    rules = classifier.load_classifier_rules()

    assert classifier.contains_answer_reveal(
        "Subtracting gives five.",
        "x = 5",
        rules,
    ) is False
    assert classifier.contains_answer_reveal(
        "Subtracting gives 5.",
        "x = 5",
        rules,
    ) is True


def test_single_choice_reveal_requires_a_standalone_choice_token() -> None:
    rules = classifier.load_classifier_rules()

    assert classifier.contains_answer_reveal(
        "Explain briefly why the variable can change.",
        "B",
        rules,
    ) is False
    assert classifier.contains_answer_reveal(
        "The correct option is B.",
        "B",
        rules,
    ) is True


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
                missing_concept_ids=["CONCEPT_EXPLANATION_OF_OPERATION"],
                selected_error_code=None,
                confidence=0.96,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["CONCEPT_EXPLANATION_OF_OPERATION"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["CONCEPT_EXPLANATION_OF_OPERATION"],
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
            "response_patterns": ["c + d"],
        }
    ]


def test_guided_partial_without_confirmed_concepts_becomes_safe_unclear(
    monkeypatch,
) -> None:
    class _InconsistentGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["OPERATION", "EXPANDED_MEANING"],
                selected_error_code=None,
                confidence=0.92,
                next_objective=kwargs["active_objective"],
                tutor_message="You have part of the idea.",
                tutor_message_voice="You have part of the idea.",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _InconsistentGuidedClient(),
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

    assert response.guided_student_state == "UNCLEAR"
    assert response.student_model_events == []
    assert response.attempt_increment == 0
    assert response.question_completed is False
    assert response.tutor_message == "State the remaining idea in your own words."


def test_guided_error_definitions_preserve_student_model_metadata() -> None:
    definitions = classifier.guided_error_definitions(
        [
            {
                "error_code": "ERR-T02-POWER-AS-COEFFICIENT",
                "error_description": "Treats the exponent as a coefficient.",
                "response_patterns": ["2pq", 123],
            }
        ]
    )

    assert definitions == [
        {
            "error_code": "ERR-T02-POWER-AS-COEFFICIENT",
            "description": "Treats the exponent as a coefficient.",
            "response_patterns": ["2pq"],
        }
    ]


def test_guided_multipart_canonical_answer_cannot_be_downgraded_by_llm(
    monkeypatch,
) -> None:
    calls = 0

    class _PartialGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _multipart_guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            nonlocal calls
            calls += 1
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["GENERAL_RULE"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["CHANGING_VALUE", "FIXED_INCREMENT"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=kwargs["active_objective"],
                tutor_message="What else changes?",
                tutor_message_voice="What else changes?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _PartialGuidedClient(),
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
            student_input="c + 4; c changes; +4 stays fixed",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert calls == 1
    assert response.evaluation == "CORRECT"
    assert response.guided_student_state == "CORRECT"
    assert response.question_completed is True
    assert response.attempt_increment == 1
    assert response.active_teaching_objective is None
    assert response.recommended_conversation_action == "ADVANCE_TO_NEXT_QUESTION"


def test_guided_multipart_undetermined_paraphrase_still_uses_llm(monkeypatch) -> None:
    calls = 0

    class _SemanticGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _multipart_guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            nonlocal calls
            calls += 1
            assert kwargs["deterministic_evaluation"] is None
            return GuidedEvaluation(
                student_state="CORRECT",
                newly_confirmed_concept_ids=[
                    "REQUIRED_COMPONENT_1",
                    "REQUIRED_COMPONENT_2",
                    "REQUIRED_COMPONENT_3",
                ],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=[],
                selected_error_code=None,
                confidence=0.98,
                next_objective=None,
                tutor_message="Yes, that describes the complete rule.",
                tutor_message_voice="Yes, that describes the complete rule.",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _SemanticGuidedClient(),
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
            student_input=(
                "The counter can start at different values, and every time "
                "you add four to it."
            ),
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert calls == 1
    assert response.evaluation == "CORRECT"
    assert response.question_completed is True


def test_guided_component_tokens_accept_canvas_role_labels() -> None:
    canvas_tokens = classifier.component_evidence_tokens(
        "m means change; 7 means fixed; operation means +"
    )

    assert classifier.component_evidence_tokens(
        "m is the changing quantity"
    ).issubset(canvas_tokens)
    assert classifier.component_evidence_tokens(
        "7 is the fixed value"
    ).issubset(canvas_tokens)
    assert classifier.component_evidence_tokens(
        "+ is the addition operation"
    ).issubset(canvas_tokens)


def test_non_multipart_deterministic_correct_stays_outside_guided_llm(
    monkeypatch,
) -> None:
    class _UnexpectedGuidedClient:
        def generate_guided_rubric(self, **kwargs):
            raise AssertionError("Non-multipart deterministic answers must not use the guided LLM.")

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _UnexpectedGuidedClient(),
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
            student_input="c times d",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.evaluation == "CORRECT"
    assert response.question_completed is True


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
                newly_confirmed_concept_ids=[
                    "REQUIRED_COMPONENT_1",
                    "REQUIRED_COMPONENT_2",
                ],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["REQUIRED_COMPONENT_3"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_CONCEPT",
                    target_concept_ids=["REQUIRED_COMPONENT_3"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["REQUIRED_COMPONENT_3"],
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

    assert captured == {"evaluation_question_type": "MULTI_PART_SHORT_RESPONSE"}
    assert response.guided_student_state == "PARTIAL"
    assert response.student_model_events == []
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.confirmed_concept_ids == [
        "REQUIRED_COMPONENT_1",
        "REQUIRED_COMPONENT_2",
    ]
    assert response.active_teaching_objective.missing_concept_ids == [
        "REQUIRED_COMPONENT_3"
    ]


def test_guided_multipart_completes_from_accumulated_component_evidence(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def evaluate_guided_turn(self, **kwargs):
            if kwargs["student_response"] == "c + 4 and c changes":
                return GuidedEvaluation(
                    student_state="PARTIAL",
                    newly_confirmed_concept_ids=[
                        "REQUIRED_COMPONENT_1",
                        "REQUIRED_COMPONENT_2",
                    ],
                    preserved_concept_ids=[],
                    contradicted_concept_ids=[],
                    missing_concept_ids=["REQUIRED_COMPONENT_3"],
                    selected_error_code=None,
                    confidence=0.98,
                    next_objective=None,
                    tutor_message="What changes and what stays fixed?",
                    tutor_message_voice="What changes and what stays fixed?",
                )
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[
                    "REQUIRED_COMPONENT_1",
                    "REQUIRED_COMPONENT_2",
                ],
                contradicted_concept_ids=[],
                missing_concept_ids=["REQUIRED_COMPONENT_3"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=None,
                tutor_message="Can you express the starting counter value?",
                tutor_message_voice="Can you express the starting counter value?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    common_request = {
        "question_id": "Q-T01-006",
        "question": (
            "A counter starts at any value c and increases by 4. "
            "Write the general rule and state what changes and what stays fixed."
        ),
        "question_type": "MULTI_PART_SHORT_RESPONSE",
        "correct_answer": "c + 4; c changes; +4 stays fixed",
        "answer_spec": _answer_spec(
            "c + 4; c changes; +4 stays fixed",
            ["c+4", "c is changing", "add 4 stays fixed"],
            "STRUCTURED_TEXT_AND_SYMBOLIC_MATCH",
        ),
        "phase_2_prompt_context": _guided_context(0),
        "current_phase": "GUIDED_PRACTICE",
        "input_source": "TEXT",
        "transcript_confidence": None,
        "attempt_count": 1,
        "current_hint_level": None,
    }
    first = classify_student_response(
        ClassificationRequest(student_input="c + 4 and c changes", **common_request)
    )
    second = classify_student_response(
        ClassificationRequest(
            student_input="+4 is fixed",
            generated_question_rubric=first.generated_question_rubric,
            active_teaching_objective=first.active_teaching_objective,
            **common_request,
        )
    )

    assert first.guided_student_state == "PARTIAL"
    assert second.guided_student_state == "CORRECT"
    assert second.active_teaching_objective is None
    assert second.question_completed is True
    assert second.recommended_conversation_action == "ADVANCE_TO_NEXT_QUESTION"


def test_guided_multipart_expression_starts_the_next_specific_teaching_step(
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
                newly_confirmed_concept_ids=["REQUIRED_COMPONENT_1"],
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
            student_input="c + 4",
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
    assert response.question_completed is False
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.confirmed_concept_ids == [
        "REQUIRED_COMPONENT_1"
    ]
    assert response.active_teaching_objective.missing_concept_ids == [
        "REQUIRED_COMPONENT_2",
        "REQUIRED_COMPONENT_3",
    ]
    assert "Which part can take different possible values?" in response.tutor_message


@pytest.mark.parametrize(
    (
        "question_type",
        "question",
        "canonical_answer",
        "verification_method",
        "student_input",
    ),
    [
        (
            "CHOICE_WITH_EXPLANATION",
            "Which statement is correct? Select one and explain why.",
            "option b",
            "EXACT_CHOICE_MATCH",
            "B",
        ),
        (
            "TRUE_FALSE_WITH_EXPLANATION",
            "True or false: In 4x, 4 is added to x. Explain.",
            "false",
            "BOOLEAN_AND_CONCEPT_MATCH",
            "false",
        ),
    ],
)
def test_explanation_question_does_not_complete_from_the_answer_alone(
    monkeypatch,
    question_type,
    question,
    canonical_answer,
    verification_method,
    student_input,
) -> None:
    captured: dict[str, object] = {}

    class _GuidedClient:
        def evaluate_guided_turn(self, **kwargs):
            captured["evaluation_question_type"] = kwargs["question_type"]
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=["ANSWER_SELECTION"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=["ANSWER_EXPLANATION"],
                selected_error_code=None,
                confidence=0.98,
                next_objective=ActiveTeachingObjective(
                    objective_type="EXPLAIN_REASONING",
                    target_concept_ids=["ANSWER_EXPLANATION"],
                    confirmed_concept_ids=[],
                    missing_concept_ids=["ANSWER_EXPLANATION"],
                ),
                tutor_message="That answer is selected. What mathematical reason supports it?",
                tutor_message_voice="That answer is selected. What mathematical reason supports it?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-EXPLANATION",
            question_type=question_type,
            question=question,
            correct_answer=canonical_answer,
            answer_spec=AnswerSpec(
                answer_spec_id="ANS-EXPLANATION",
                canonical_answer=canonical_answer,
                accepted_answers=[canonical_answer],
                verification_method=verification_method,
                explanation_required=True,
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

    assert captured == {"evaluation_question_type": question_type}
    assert response.guided_student_state == "PARTIAL"
    assert response.question_completed is False
    assert response.student_model_events == []
    assert response.active_teaching_objective is not None
    assert response.active_teaching_objective.confirmed_concept_ids == [
        "ANSWER_SELECTION"
    ]
    assert response.active_teaching_objective.missing_concept_ids == [
        "ANSWER_EXPLANATION"
    ]


@pytest.mark.parametrize(
    "question_type",
    ["CHOICE_WITH_EXPLANATION", "TRUE_FALSE_WITH_EXPLANATION"],
)
def test_explanation_question_uses_a_stable_two_component_rubric(
    question_type,
) -> None:
    rubric = classifier.rubric_from_authored_answer_parts(
        question_id="Q-EXPLANATION",
        question_type=question_type,
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-EXPLANATION",
            canonical_answer="B",
            accepted_answers=["B"],
            verification_method="CHOICE_AND_CONCEPT_MATCH",
            explanation_required=True,
        ),
        prompt_version="1.1.0",
    )

    assert rubric is not None
    assert [
        component.concept_id for component in rubric.required_concepts
    ] == ["ANSWER_SELECTION", "ANSWER_EXPLANATION"]


def test_component_adjudication_ignores_an_already_confirmed_claim() -> None:
    rubric = GeneratedQuestionRubric(
        question_id="Q-EXPLANATION",
        required_concepts=[
            GeneratedConcept(
                concept_id="ANSWER_SELECTION",
                description="Selects the correct answer.",
                required=True,
            ),
            GeneratedConcept(
                concept_id="ANSWER_EXPLANATION",
                description="Explains why the selected answer is true.",
                required=True,
            ),
        ],
        completion_rule="ALL_REQUIRED_CONCEPTS",
        cache_key="explanation-rubric",
        prompt_version="1.1.0",
    )
    objective = ActiveTeachingObjective(
        objective_type="EXPLAIN_REASONING",
        target_concept_ids=["ANSWER_EXPLANATION"],
        confirmed_concept_ids=["ANSWER_SELECTION"],
        missing_concept_ids=["ANSWER_EXPLANATION"],
    )
    evaluation = GuidedEvaluation(
        student_state="PARTIAL",
        newly_confirmed_concept_ids=["ANSWER_SELECTION"],
        preserved_concept_ids=["ANSWER_SELECTION"],
        contradicted_concept_ids=[],
        missing_concept_ids=["ANSWER_EXPLANATION"],
        selected_error_code=None,
        confidence=0.95,
        next_objective=objective,
        tutor_message="Explain why.",
        tutor_message_voice="Explain why.",
    )

    targets = classifier.component_adjudication_targets(
        evaluation=evaluation,
        objective=objective,
        rubric=rubric,
        student_response="because n is a variable",
        question="Which is the general rule: 12 + 4 or n + 4? Explain why.",
        answer_spec=AnswerSpec(
            answer_spec_id="ANS-EXPLANATION",
            canonical_answer="n + 4",
            accepted_answers=["n + 4 because n can vary"],
            verification_method="CHOICE_AND_CONCEPT_MATCH",
            explanation_required=True,
        ),
    )

    assert [target.concept_id for target in targets] == ["ANSWER_EXPLANATION"]


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
    assert response.response_strategy == "CLARIFY"
    assert response.student_model_events == []
    assert response.attempt_increment == 0


def test_guided_wrong_at_configured_confidence_requests_student_model_support(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric().model_copy(
                update={"question_id": "Q-T02-003"}
            )

        def evaluate_guided_turn(self, **kwargs):
            assert kwargs["deterministic_evaluation"] == "INCORRECT"
            return GuidedEvaluation(
                student_state="WRONG",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=[],
                selected_error_code="ERR-T02-ADDITION",
                confidence=0.5,
                next_objective=kwargs["active_objective"],
                tutor_message="That interpretation uses addition. What operation does cd represent?",
                tutor_message_voice="That interpretation uses addition. What operation does c d represent?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-003",
            question="Write p × p × q in compact algebraic notation.",
            correct_answer="p²q",
            answer_spec=_answer_spec(
                "p²q",
                ["p^2q"],
                "EXACT_NOTATION_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="p^q",
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


def test_guided_partial_with_only_authored_error_evidence_counts_as_wrong(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric().model_copy(
                update={"question_id": "Q-T02-003"}
            )

        def evaluate_guided_turn(self, **kwargs):
            objective = kwargs["active_objective"]
            return GuidedEvaluation(
                student_state="PARTIAL",
                newly_confirmed_concept_ids=[],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=objective.missing_concept_ids,
                selected_error_code="ERR-T02-ADDITION",
                confidence=0.97,
                next_objective=objective,
                tutor_message="That uses addition. Which operation is required?",
                tutor_message_voice="That uses addition. Which operation is required?",
            )

    monkeypatch.setattr(
        classifier,
        "build_openai_ai_engine_client",
        lambda settings: _GuidedClient(),
    )
    response = classify_student_response(
        ClassificationRequest(
            question_id="Q-T02-003",
            question="Write p × p × q in compact algebraic notation.",
            correct_answer="p²q",
            answer_spec=_answer_spec(
                "p²q",
                ["p^2q"],
                "EXACT_NOTATION_MATCH",
            ),
            phase_2_prompt_context=_guided_context(0),
            student_input="p + q",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=4,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "WRONG"
    assert response.selected_error_code == "ERR-T02-ADDITION"
    assert response.attempt_increment == 1


def test_guided_explicit_stuck_is_not_downgraded_by_semantic_confidence(
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
                confidence=0.0,
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
            input_source="VOICE",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "STUCK"
    assert response.response_strategy == "CLARIFY"
    assert response.attempt_increment == 0


def test_guided_correct_keeps_the_strict_confidence_threshold(
    monkeypatch,
) -> None:
    class _GuidedClient:
        def generate_guided_rubric(self, **kwargs):
            return _guided_rubric()

        def evaluate_guided_turn(self, **kwargs):
            return GuidedEvaluation(
                student_state="CORRECT",
                newly_confirmed_concept_ids=["OPERATION", "EXPANDED_MEANING"],
                preserved_concept_ids=[],
                contradicted_concept_ids=[],
                missing_concept_ids=[],
                selected_error_code=None,
                confidence=0.7,
                next_objective=None,
                tutor_message="That explains the meaning.",
                tutor_message_voice="That explains the meaning.",
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
            student_input="It indicates multiplication.",
            current_phase="GUIDED_PRACTICE",
            input_source="TEXT",
            transcript_confidence=None,
            attempt_count=1,
            current_hint_level=None,
        )
    )

    assert response.guided_student_state == "UNCLEAR"
    assert response.attempt_increment == 0
    assert response.question_completed is False


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
        "That's okay. State the remaining idea in your own words."
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


def test_guided_rubric_uses_phase_prompt_and_specialized_contract(
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
    assert messages[0]["role"] == "system"
    assert "Nablix AI Math Tutor" in messages[0]["content"]
    assert messages[1]["role"] == "system"
    assert "PHASE 2" in messages[1]["content"]
    assert messages[3] == {"role": "system", "content": system_prompt}
    assert messages[-1]["role"] == "user"


def test_focused_component_schema_requires_the_requested_component_id() -> None:
    schema = openai_client.focused_component_evidence_schema(
        "CONCEPT-NUMERIC_CASE"
    )
    properties = schema["properties"]
    assert isinstance(properties, dict)
    component_id = properties["component_id"]
    assert isinstance(component_id, dict)
    assert component_id["enum"] == ["CONCEPT-NUMERIC_CASE"]


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
