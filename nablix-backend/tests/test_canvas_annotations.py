import pytest

from app.ai_engine.classifier_config import FallbackCanvasLabelsConfig, load_classifier_rules
from app.models.adapters import (
    AnnotationIntent,
    OCRTextRegion,
    SpatialMathToken,
    TutorMistakeClassification,
    TutorResult,
)
from app.models.canvas import TutorElement
from app.models.canvas_memory import CanvasEvent
from app.models.guided_learning import (
    ActiveTeachingObjective,
    CanvasPedagogyIntent,
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedTeachingState,
)
from app.models.question_anchor import QuestionTextAnchor
from pydantic import ValidationError
from app.services.canvas_annotations import (
    assign_step_ids,
    plan_canvas_draw,
    plan_tutor_canvas_actions,
    plan_write_request_tutor_draw,
)


def _fallback_labels() -> FallbackCanvasLabelsConfig:
    return load_classifier_rules().guided_learning.fallback_canvas_labels


def _tutor_result(
    classification: TutorMistakeClassification,
    annotation_intents: list[AnnotationIntent],
) -> TutorResult:
    return TutorResult(
        evaluation="INCORRECT",
        error_type="ARITHMETIC_ERROR",
        intent="SUBMITTING_ANSWER",
        response_strategy="GUIDED_HINT",
        tutor_message="Subtract 4, not 5.",
        tutor_message_voice="Subtract 4, not 5.",
        voice_optimised=True,
        hint_level=1,
        answer_reveal_allowed=False,
        confidence=0.9,
        input_source="CANVAS",
        mistake_classification=classification,
        annotation_intents=annotation_intents,
        attempt_increment=1,
        recommended_conversation_action="GIVE_HINT",
        question_completed=False,
    )


def _region() -> OCRTextRegion:
    return OCRTextRegion(
        text="x = 9 - 5",
        x=0.12,
        y=0.30,
        w=0.34,
        h=0.08,
        confidence=0.95,
    )


def _intents() -> list[AnnotationIntent]:
    return [
        AnnotationIntent(kind="circle_target", target_step_id="step-1"),
        AnnotationIntent(
            kind="write_correction",
            target_step_id="step-1",
            text="x = 9 - 4",
            placement="right",
        ),
        AnnotationIntent(kind="draw_arrow", target_step_id="step-1"),
    ]


def _token() -> SpatialMathToken:
    return SpatialMathToken(
        token_id="step-1:token-1",
        step_id="step-1",
        text="x",
        bounding_box={"x": 0.12, "y": 0.30, "width": 0.05, "height": 0.08},
        alignment_confidence=0.95,
    )


def _ellipse_from(elements: list[TutorElement]) -> TutorElement:
    ellipse = next(element for element in elements if element.kind == "ellipse")
    assert ellipse.x is not None
    assert ellipse.w is not None
    return ellipse


def test_canvas_planner_does_not_mark_without_grounded_tokens() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="5",
            target_span=(8, 9),
            replacement_text="4",
            confidence=0.86,
        ),
        _intents(),
    )

    assert plan_canvas_draw(tutor, regions) == []


def test_canvas_planner_does_not_mark_without_grounded_tokens_when_no_correction_intent() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="5",
            target_span=(8, 9),
            replacement_text=None,
            confidence=0.86,
        ),
        [AnnotationIntent(kind="circle_target", target_step_id="step-1")],
    )

    assert plan_canvas_draw(tutor, regions) == []


def test_canvas_planner_circles_explicit_whole_line_mistake() -> None:
    regions = assign_step_ids([_region()])
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_text="x = 9 - 5",
            target_span=None,
            replacement_text=None,
            confidence=0.95,
        ),
        [AnnotationIntent(kind="circle_target", target_step_id="step-1")],
    )

    draw = plan_canvas_draw(tutor, regions, [_token()])

    assert len(draw) == 1
    assert draw[0].action_id == "canvas-line-review-step-1"
    assert [element.kind for element in draw[0].elements] == ["ellipse"]


def test_confirmed_guided_idea_emits_a_component_scoped_semantic_action() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "answer_value_confirmed": False,
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=["CHANGING_VALUE"],
                confirmed_concept_ids=["CHANGING_VALUE"],
                missing_concept_ids=["FIXED_VALUE"],
            ),
            "guided_teaching_state": GuidedTeachingState(
                question_id="Q-T01-002",
                objective_component_ids=["CHANGING_VALUE", "FIXED_VALUE"],
                confirmed_component_ids=["CHANGING_VALUE"],
                missing_component_ids=["FIXED_VALUE"],
                active_component_id="FIXED_VALUE",
                last_tutor_question_type="COMPONENT",
                selected_option_id=None,
                awaiting_response=True,
            ),
            "canvas_intentions": [
                CanvasPedagogyIntent(
                    action_type="INSERT_LABEL",
                    target_kind="QUESTION_ANCHOR",
                    target_object_id="Q-T01-002:QTOKEN:1",
                    confirmed_component_id="CHANGING_VALUE",
                    text="m → changes",
                    source_id=None,
                )
            ],
        }
    )

    actions = plan_tutor_canvas_actions(
        tutor,
        [QuestionTextAnchor(token_id="Q-T01-002:QTOKEN:1", text="m", char_start=0, char_end=1)],
        [],
        "TURN-1",
        "m + 7",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert actions[0].type == "INSERT_LABEL"
    assert actions[0].text == "m → changes"
    assert actions[0].answer_reveal_allowed is False


def test_accepted_student_statement_gets_a_tutor_layer_label_without_llm_intention() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(update={"guided_student_state": "PARTIAL"})
    anchor = QuestionTextAnchor(
        token_id="Q-T01-002:QTOKEN:2",
        text="m",
        char_start=3,
        char_end=4,
    )

    actions = plan_tutor_canvas_actions(
        tutor=tutor,
        question_anchors=[anchor],
        canvas_events=[],
        turn_id="TURN-accepted",
        canonical_answer="m; 7; addition",
        fallback_labels=_fallback_labels(),
        wrong_attempt_count=0,
        student_response="m changes",
    )

    assert [(action.target_kind, action.target_object_id, action.text) for action in actions] == [
        ("QUESTION_ANCHOR", "Q-T01-002:QTOKEN:2", "m → changes"),
        ("TUTOR_ANCHOR", "TUTOR_ANCHOR:CONFIRMED:Q-T01-002:1", "m → changes"),
    ]


def test_accepted_fixed_value_and_operation_get_tutor_layer_labels() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(update={"guided_student_state": "PARTIAL"})
    anchors = [
        QuestionTextAnchor(
            token_id="Q-T01-002:QTOKEN:2",
            text="+",
            char_start=4,
            char_end=5,
        ),
        QuestionTextAnchor(
            token_id="Q-T01-002:QTOKEN:3",
            text="7",
            char_start=6,
            char_end=7,
        ),
    ]

    actions = plan_tutor_canvas_actions(
        tutor=tutor,
        question_anchors=anchors,
        canvas_events=[],
        turn_id="TURN-fixed-operation",
        canonical_answer="m; 7; addition",
        fallback_labels=_fallback_labels(),
        wrong_attempt_count=0,
        student_response="7 is fixed and the plus sign means addition",
    )

    assert [(action.target_object_id, action.text) for action in actions] == [
        ("Q-T01-002:QTOKEN:3", "7 → stays fixed"),
        ("Q-T01-002:QTOKEN:2", "+ → addition"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:1", "7 → stays fixed"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:2", "+ → addition"),
    ]


def test_canvas_action_rejects_unconfirmed_target_and_answer_reveal_text() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=["CHANGING_VALUE"],
                confirmed_concept_ids=[],
                missing_concept_ids=["CHANGING_VALUE"],
            ),
            "canvas_intentions": [
                CanvasPedagogyIntent(
                    action_type="INSERT_MATH",
                    target_kind="QUESTION_ANCHOR",
                    target_object_id="unknown",
                    confirmed_component_id="CHANGING_VALUE",
                    text="n + 5",
                    source_id=None,
                )
            ],
        }
    )

    assert plan_tutor_canvas_actions(
        tutor,
        [],
        [],
        "TURN-1",
        "n + 5",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    ) == []


def test_wrong_turn_targets_only_reliable_student_written_work() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(update={"guided_student_state": "WRONG"})
    actions = plan_tutor_canvas_actions(
        tutor,
        [],
        [
            CanvasEvent(
                order_index=0,
                turn_id="TURN-1",
                question_id="Q-T01-001",
                actor="STUDENT",
                action_type="WRITE",
                content="5n",
                math_text="5n",
                target_object_id="student-5n",
                bbox=None,
                semantic_tag="student_attempt",
                source_id=None,
                active_state="ACTIVE",
            )
        ],
        "TURN-1",
        "n + 5",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert [(action.type, action.target_object_id) for action in actions] == [
        ("HIGHLIGHT", "student-5n")
    ]


def test_partial_choice_selection_gets_a_stable_option_action() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="ANSWER_QUESTION",
                target_concept_ids=["ANSWER_EXPLANATION"],
                confirmed_concept_ids=["ANSWER_SELECTION"],
                missing_concept_ids=["ANSWER_EXPLANATION"],
            ),
            "guided_teaching_state": GuidedTeachingState(
                question_id="Q-T01-004",
                objective_component_ids=["ANSWER_SELECTION", "ANSWER_EXPLANATION"],
                confirmed_component_ids=["ANSWER_SELECTION"],
                missing_component_ids=["ANSWER_EXPLANATION"],
                active_component_id="ANSWER_EXPLANATION",
                last_tutor_question_type="COMPONENT",
                selected_option_id="B",
                awaiting_response=True,
            ),
        }
    )

    actions = plan_tutor_canvas_actions(
        tutor,
        [],
        [],
        "TURN-1",
        "n + 4",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert [(action.type, action.target_kind, action.target_object_id) for action in actions] == [
        ("HIGHLIGHT", "QUESTION_OPTION", "Q-T01-004:OPTION:B")
    ]


def test_fallback_turn_labels_every_confirmed_expression_component() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=["OPERATION"],
                confirmed_concept_ids=[
                    "CHANGING_VALUE",
                    "FIXED_VALUE",
                    "OPERATION",
                ],
                missing_concept_ids=["OPERATION"],
            ),
        }
    )
    anchors = [
        QuestionTextAnchor(token_id="Q-T01-002:QTOKEN:1", text="m", char_start=3, char_end=4),
        QuestionTextAnchor(token_id="Q-T01-002:QTOKEN:2", text="+", char_start=5, char_end=6),
        QuestionTextAnchor(token_id="Q-T01-002:QTOKEN:3", text="7", char_start=7, char_end=8),
    ]

    actions = plan_tutor_canvas_actions(
        tutor,
        anchors,
        [],
        "TURN-1",
        "m + 7",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert [(action.target_object_id, action.text) for action in actions] == [
        ("Q-T01-002:QTOKEN:1", "m → changes"),
        ("Q-T01-002:QTOKEN:3", "7 → stays fixed"),
        ("Q-T01-002:QTOKEN:2", "+ → addition"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:1", "m → changes"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:2", "7 → stays fixed"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:3", "+ → addition"),
    ]


def test_fallback_turn_does_not_repeat_an_active_confirmation_label() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=["FIXED_VALUE"],
                confirmed_concept_ids=["CHANGING_VALUE"],
                missing_concept_ids=["FIXED_VALUE"],
            ),
        }
    )
    anchor = QuestionTextAnchor(
        token_id="Q-T01-002:QTOKEN:1",
        text="m",
        char_start=3,
        char_end=4,
    )
    active_label = CanvasEvent(
        order_index=0,
        turn_id="TURN-1",
        question_id="Q-T01-002",
        actor="TUTOR",
        action_type="INSERT_LABEL",
        content="m → changes",
        math_text=None,
        target_object_id=anchor.token_id,
        bbox=None,
        semantic_tag="CHANGING_VALUE",
        source_id="TURN-1:1:INSERT_LABEL:Q-T01-002:QTOKEN:1",
        active_state="ACTIVE",
    )

    actions = plan_tutor_canvas_actions(
        tutor,
        [anchor],
        [active_label],
        "TURN-2",
        "m + 7",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert actions == []


def test_fallback_turn_handles_non_expression_canonical_answers() -> None:
    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "active_teaching_objective": ActiveTeachingObjective(
                objective_type="EXPLAIN_CONCEPT",
                target_concept_ids=["RCO2"],
                confirmed_concept_ids=["RCO1"],
                missing_concept_ids=["RCO2"],
            ),
            "generated_question_rubric": GeneratedQuestionRubric(
                question_id="Q-T01-002",
                required_concepts=[
                    GeneratedConcept(
                        concept_id="RCO1",
                        description="m changes",
                        required=True,
                    )
                ],
                completion_rule="ALL_REQUIRED_CONCEPTS",
                cache_key="m-plus-seven",
                prompt_version="1.0.0",
            ),
        }
    )
    anchor = QuestionTextAnchor(
        token_id="Q-T01-002:QTOKEN:1",
        text="m",
        char_start=3,
        char_end=4,
    )

    actions = plan_tutor_canvas_actions(
        tutor,
        [anchor],
        [],
        "TURN-1",
        "changing quantity, fixed value, and operation",
        _fallback_labels(),
        wrong_attempt_count=0,
        student_response="",
    )

    assert [(action.target_object_id, action.text) for action in actions] == [
        ("Q-T01-002:QTOKEN:1", "m → changes"),
        ("TUTOR_ANCHOR:CONFIRMED:Q-T01-002:1", "m → changes"),
    ]


def test_semantic_canvas_action_contract_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        CanvasPedagogyIntent.model_validate(
            {
                "action_type": "DRAW_RECTANGLE",
                "target_kind": "QUESTION_ANCHOR",
                "target_object_id": "Q-T01-001:QTOKEN:1",
                "confirmed_component_id": "FIXED_VALUE",
                "text": "+5 → stays fixed",
                "source_id": None,
            }
        )


def test_write_request_marks_a_tutor_owned_area_without_revealing_the_rule() -> None:
    draw = plan_write_request_tutor_draw("TURN-1")

    assert [element.kind for element in draw[0].elements] == ["highlight", "text", "arrow"]
    assert all("s + 6" not in (element.text or "") for element in draw[0].elements)


def test_write_request_on_first_attempt_has_no_rule_anchors() -> None:
    """First attempt is clean evidence: no Start/Gain scaffolding to copy from."""

    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "requires_written_math_evidence": True,
        }
    )

    actions = plan_tutor_canvas_actions(
        tutor, [], [], "TURN-1", "s + 6", _fallback_labels(), wrong_attempt_count=0, student_response=""
    )

    assert [(action.type, action.text) for action in actions] == [
        ("FOCUS", "Write your rule on the canvas."),
    ]


def test_written_rule_request_adds_safe_tutor_anchors_not_the_final_rule() -> None:
    """After a failed attempt, the rule parts appear as scaffolding."""

    tutor = _tutor_result(
        TutorMistakeClassification(status="no_mistake", confidence=0.9),
        [],
    ).model_copy(
        update={
            "guided_student_state": "PARTIAL",
            "requires_written_math_evidence": True,
        }
    )

    actions = plan_tutor_canvas_actions(
        tutor, [], [], "TURN-1", "s + 6", _fallback_labels(), wrong_attempt_count=1, student_response=""
    )

    assert [(action.type, action.text) for action in actions] == [
        ("INSERT_LABEL", "Start: s"),
        ("INSERT_LABEL", "Gain: +6"),
        ("FOCUS", "Write your rule on the canvas."),
    ]
    assert all(action.text != "s + 6" for action in actions)


def test_canvas_planner_uses_target_token_geometry() -> None:
    regions = assign_step_ids(
        [
            OCRTextRegion(
                text="c - 4",
                x=0.10,
                y=0.30,
                w=0.40,
                h=0.08,
                confidence=0.95,
            )
        ]
    )
    tutor = _tutor_result(
        TutorMistakeClassification(
            status="mistake_found",
            mistake_step_id="step-1",
            target_token_ids=["step-1:token-2"],
            error_token="-",
            expected_token="+",
            target_text="-",
            replacement_text="+",
            confidence=0.95,
        ),
        [
            AnnotationIntent(kind="circle_target", target_step_id="step-1"),
            AnnotationIntent(
                kind="write_correction",
                target_step_id="step-1",
                text="+",
                placement="right",
            ),
            AnnotationIntent(kind="draw_arrow", target_step_id="step-1"),
        ],
    )
    draw = plan_canvas_draw(
        tutor,
        regions,
        [
            SpatialMathToken(
                token_id="step-1:token-1",
                step_id="step-1",
                text="c",
                bounding_box={"x": 0.10, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-2",
                step_id="step-1",
                text="-",
                bounding_box={"x": 0.20, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
            SpatialMathToken(
                token_id="step-1:token-3",
                step_id="step-1",
                text="4",
                bounding_box={"x": 0.30, "y": 0.30, "width": 0.05, "height": 0.08},
                alignment_confidence=0.95,
            ),
        ],
    )

    assert [element.kind for element in draw[0].elements] == [
        "ellipse",
        "math",
        "arrow",
    ]
    assert abs(draw[0].elements[0].w - 0.05) < 1e-9
    assert abs(draw[0].elements[0].h - 0.08) < 1e-9
