import pytest

from app.ai_engine.classifier_config import load_classifier_rules
from app.core.config import Settings
from app.models.adapters import TutorResult
from app.models.canvas_teaching import CanvasTeachingPlanDraft
from app.models.guided_learning import (
    GeneratedConcept,
    GeneratedQuestionRubric,
    GuidedEvidenceClaim,
    GuidedTeachingState,
    StudentContribution,
    TutorCanvasAction,
)
from app.models.question_anchor import QuestionTextAnchor
from app.services.question_anchors import question_text_tokens
from app.services import canvas_teaching_planner


class FakeCanvasTeachingClient:
    def __init__(self, draft: CanvasTeachingPlanDraft) -> None:
        self.draft = draft

    def plan_canvas_teaching(
        self,
        system_prompt: str,
        context: dict[str, object],
    ) -> CanvasTeachingPlanDraft:
        assert system_prompt
        assert context["question_id"] == "Q1"
        return self.draft


def _tutor(contribution: StudentContribution | None = None) -> TutorResult:
    return TutorResult(
        evaluation="PARTIALLY_CORRECT",
        error_type="NONE",
        intent="SUBMITTING_ANSWER",
        response_strategy="GUIDED_HINT",
        tutor_message="Those first numbers are different.",
        tutor_message_voice="Those first numbers are different.",
        voice_optimised=True,
        hint_level=0,
        answer_reveal_allowed=False,
        confidence=0.9,
        input_source="TEXT",
        attempt_increment=0,
        recommended_conversation_action="REQUEST_CLARIFICATION",
        question_completed=False,
        guided_teaching_state=GuidedTeachingState(
            question_id="Q1",
            objective_component_ids=["CHANGING_VALUE", "FIXED_VALUE"],
            confirmed_component_ids=["CHANGING_VALUE"],
            missing_component_ids=["FIXED_VALUE"],
            active_component_id="FIXED_VALUE",
            last_tutor_question_type="COMPONENT",
            selected_option_id=None,
            awaiting_response=True,
            last_turn_evidence=[
                GuidedEvidenceClaim(
                    concept_id="CHANGING_VALUE",
                    status="DEMONSTRATED",
                    source="TEXT",
                )
            ],
        ),
        contribution=contribution,
    )


def _enabled_rules() -> object:
    rules = load_classifier_rules()
    canvas_teaching = rules.guided_learning.canvas_teaching.model_copy(
        update={"enabled": True}
    )
    guided_learning = rules.guided_learning.model_copy(
        update={"canvas_teaching": canvas_teaching}
    )
    return rules.model_copy(update={"guided_learning": guided_learning})


def _anchor() -> QuestionTextAnchor:
    return QuestionTextAnchor(
        token_id="Q1:QTOKEN:1",
        text="3",
        char_start=0,
        char_end=1,
    )


def _plan(
    draft: CanvasTeachingPlanDraft,
    tutor: TutorResult | None = None,
    voice: str = "Those first numbers are different.",
    active_support_level: str | None = None,
) -> object:
    return canvas_teaching_planner.plan_canvas_teaching(
        question_id="Q1",
        question="3 + 5 | 9 + 5 | 14 + 5",
        source_turn_id="TURN-1",
        tutor_turn_id="TUTOR-1",
        scene_revision=3,
        tutor_message_voice=voice,
        tutor=tutor or _tutor(),
        question_anchors=[_anchor()],
        student_response="They are different.",
        canonical_answer="n + 5",
        active_support_level=active_support_level,
        current_unresolved_component_id="FIXED_VALUE",
    )


def _plan_for_question_anchor(
    draft: CanvasTeachingPlanDraft,
    question_anchor: QuestionTextAnchor,
) -> object:
    return canvas_teaching_planner.plan_canvas_teaching(
        question_id="Q1",
        question="Write p × q in compact algebraic notation.",
        source_turn_id="TURN-1",
        tutor_turn_id="TUTOR-1",
        scene_revision=3,
        tutor_message_voice="Write p times q in compact algebraic notation.",
        tutor=_tutor(),
        question_anchors=[question_anchor],
        student_response="I do not know.",
        canonical_answer="pq",
        active_support_level=None,
        current_unresolved_component_id="FIXED_VALUE",
    )


def _pattern_tutor(
    evidence_id: str,
    confirmed_ids: list[str],
    answer_value_confirmed: bool = False,
) -> TutorResult:
    tutor = _tutor()
    state = tutor.guided_teaching_state
    assert state is not None
    return tutor.model_copy(
        update={
            "answer_value_confirmed": answer_value_confirmed,
            "guided_teaching_state": state.model_copy(
                update={
                    "confirmed_component_ids": confirmed_ids,
                    "last_turn_evidence": [
                        GuidedEvidenceClaim(
                            concept_id=evidence_id,
                            status="DEMONSTRATED",
                            source="TEXT",
                        )
                    ],
                }
            ),
        }
    )


def _pattern_plan(
    tutor: TutorResult,
    student_response: str,
    active_support_level: str | None = None,
    unresolved_component_id: str | None = None,
) -> object:
    question = "3 + 5 | 9 + 5 | 14 + 5. Use n for the changing starting number."
    return canvas_teaching_planner.plan_canvas_teaching(
        question_id="Q1",
        question=question,
        source_turn_id="TURN-1",
        tutor_turn_id="TUTOR-1",
        scene_revision=3,
        tutor_message_voice="Let us record that on the canvas.",
        tutor=tutor,
        question_anchors=question_text_tokens("Q1", question),
        student_response=student_response,
        canonical_answer="n + 5",
        active_support_level=active_support_level,
        current_unresolved_component_id=unresolved_component_id,
    )


def _multiplication_pattern_plan(
    tutor: TutorResult,
    student_response: str,
) -> object:
    question = "2 × 4 | 7 × 4 | 11 × 4. Use n for the changing starting number. Write the general rule."
    return canvas_teaching_planner.plan_canvas_teaching(
        question_id="Q2",
        question=question,
        source_turn_id="TURN-2",
        tutor_turn_id="TUTOR-2",
        scene_revision=4,
        tutor_message_voice="Let us record that on the canvas.",
        tutor=tutor,
        question_anchors=question_text_tokens("Q2", question),
        student_response=student_response,
        canonical_answer="n × 4",
        active_support_level=None,
        current_unresolved_component_id=None,
    )


def _tutor_solved_action(step_index: int, total_steps: int, final_step: bool) -> TutorCanvasAction:
    return TutorCanvasAction(
        action_id=f"RESCUE:step:{step_index}",
        type="TUTOR_SOLVED_STEP",
        target_kind="TUTOR_ANCHOR",
        target_object_id=f"TUTOR_ANCHOR:RESCUE:RESCUE:STEP:{step_index}",
        confirmed_component_id=None,
        text="Tutor solved pattern step.",
        source_id="pattern-rescue",
        answer_reveal_allowed=final_step,
        rescue_id="RESCUE",
        step_index=step_index,
        total_steps=total_steps,
        presentation_mode="TUTOR_SOLVED",
        return_target_object_id="TUTOR_ANCHOR:QUESTION:Q1",
    )


def test_planner_returns_a_grounded_attention_beat(monkeypatch) -> None:
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "focus-first-values",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": 19,
                        "text": "Those first numbers",
                    },
                    "operations": [
                        {
                            "operation_id": "circle-first-values",
                            "kind": "CIRCLE",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                            "color_role": "AMBER",
                        },
                        {
                            "operation_id": "write-confirmed-observation",
                            "kind": "WRITE_TEXT",
                            "target_kind": "CANVAS_ZONE",
                            "target_ids": ["ZONE:REASONING"],
                            "zone": "REASONING",
                            "persistence": "PERSIST",
                            "evidence_ref": "CHANGING_VALUE",
                            "text": "first numbers are different",
                            "color_role": "NAVY",
                            "scene_slot": "untrusted-model-slot",
                        }
                    ],
                }
            ]
        }
    )
    rules = _enabled_rules()
    requested_models: list[str] = []

    def build_client(settings: Settings) -> FakeCanvasTeachingClient:
        requested_models.append(settings.openai_ai_engine_model)
        return FakeCanvasTeachingClient(draft)

    monkeypatch.setattr(
        canvas_teaching_planner, "load_classifier_rules", lambda: rules
    )
    monkeypatch.setattr(
        canvas_teaching_planner,
        "get_settings",
        lambda: Settings(openai_ai_engine_model="general-purpose-model"),
    )
    monkeypatch.setattr(
        canvas_teaching_planner, "build_openai_ai_engine_client", build_client
    )

    plan = _plan(draft)

    assert plan is not None
    assert plan.plan_id == "Q1:TURN-1:canvas-teaching"
    assert plan.beats[0].operations[0].target_ids == ["Q1:QTOKEN:1"]
    assert plan.beats[0].operations[1].kind == "WRITE_TEXT"
    assert plan.beats[0].operations[1].scene_slot == "changing_conclusion"
    assert requested_models == [rules.guided_learning.model]


def test_pattern_scene_writes_only_after_the_learner_names_the_changing_part(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: (_ for _ in ()).throw(AssertionError("pattern scene must not call OpenAI")),
    )

    plan = _pattern_plan(
        tutor=_pattern_tutor("CHANGING_VALUE", ["CHANGING_VALUE"]),
        student_response="The starting numbers are different.",
    )

    assert plan is not None
    operations = plan.beats[0].operations
    assert [operation.kind for operation in operations] == ["CIRCLE", "WRITE_TEXT"]
    assert operations[0].target_ids == ["Q1:QTOKEN:1", "Q1:QTOKEN:4", "Q1:QTOKEN:7"]
    assert operations[1].text == "starting number → changes"
    assert operations[1].scene_slot == "changing_conclusion"


def test_pattern_scene_pulses_a_bare_fixed_value_without_writing_a_conclusion(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)

    plan = _pattern_plan(
        tutor=_pattern_tutor("FIXED_VALUE", ["CHANGING_VALUE"]),
        student_response="5",
    )

    assert plan is not None
    operations = plan.beats[0].operations
    assert all(operation.kind == "HIGHLIGHT" for operation in operations)
    assert all(operation.persistence == "PULSE" for operation in operations)


def test_pattern_scene_writes_the_fixed_conclusion_only_after_plus_value(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)

    plan = _pattern_plan(
        tutor=_pattern_tutor("FIXED_VALUE", ["CHANGING_VALUE", "FIXED_VALUE"]),
        student_response="Plus 5.",
    )

    assert plan is not None
    operations = plan.beats[0].operations
    assert any(operation.kind == "CONNECT" for operation in operations)
    write = next(operation for operation in operations if operation.kind == "WRITE_TEXT")
    assert write.text == "+5 → stays fixed"
    assert write.scene_slot == "fixed_conclusion"


def test_pattern_scene_boxes_only_the_confirmed_final_rule(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)

    plan = _pattern_plan(
        tutor=_pattern_tutor(
            "GENERAL_RULE",
            ["CHANGING_VALUE", "FIXED_VALUE", "OPERATION", "GENERAL_RULE"],
            answer_value_confirmed=True,
        ),
        student_response="n + 5",
    )

    assert plan is not None
    operation = plan.beats[0].operations[0]
    assert operation.kind == "WRITE_MATH"
    assert operation.latex == "n + 5"
    assert operation.scene_slot == "rule_conclusion"


def test_multiplication_pattern_scene_uses_the_same_evidence_gates(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)

    plan = _multiplication_pattern_plan(
        tutor=_pattern_tutor("FIXED_VALUE", ["CHANGING_VALUE", "FIXED_VALUE"]),
        student_response="times 4",
    )

    assert plan is not None
    write = next(
        operation for operation in plan.beats[0].operations if operation.kind == "WRITE_TEXT"
    )
    assert write.text == "×4 → stays fixed"
    assert write.scene_slot == "fixed_conclusion"


def test_tutor_solved_pattern_scene_reveals_only_the_current_step(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    tutor = _pattern_tutor("CHANGING_VALUE", [])
    tutor = tutor.model_copy(
        update={"tutor_canvas_actions": [_tutor_solved_action(2, 4, False)]}
    )

    plan = _pattern_plan(tutor=tutor, student_response="I do not know")

    assert plan is not None
    operations = plan.beats[0].operations
    assert any(operation.operation_id == "tutor-solved-connect-fixed-values" for operation in operations)
    assert all(operation.scene_slot != "rule_conclusion" for operation in operations)


def test_tutor_solved_pattern_scene_boxes_the_rule_only_on_final_step(monkeypatch) -> None:
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    tutor = _pattern_tutor("GENERAL_RULE", [])
    tutor = tutor.model_copy(
        update={"tutor_canvas_actions": [_tutor_solved_action(4, 4, True)]}
    )

    plan = _pattern_plan(tutor=tutor, student_response="I do not know")

    assert plan is not None
    operation = plan.beats[0].operations[0]
    assert operation.operation_id == "tutor-solved-final-rule"
    assert operation.scene_slot == "rule_conclusion"


def test_planner_rejects_attention_only_after_confirmed_guided_evidence(monkeypatch) -> None:
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "focus-first-values",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": 19,
                        "text": "Those first numbers",
                    },
                    "operations": [
                        {
                            "operation_id": "circle-first-values",
                            "kind": "CIRCLE",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                            "color_role": "AMBER",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    assert _plan(draft) is None


def test_planner_rejects_a_prose_question_annotation(monkeypatch) -> None:
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "mark-instruction",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": 5,
                        "text": "Write",
                    },
                    "operations": [
                        {
                            "operation_id": "highlight-write",
                            "kind": "HIGHLIGHT",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    plan = _plan_for_question_anchor(
        draft,
        QuestionTextAnchor(
            token_id="Q1:QTOKEN:1",
            text="Write",
            char_start=0,
            char_end=5,
        ),
    )

    assert plan is None


def test_planner_rejects_an_unapproved_final_rule(monkeypatch) -> None:
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "write-rule",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": 19,
                        "text": "Those first numbers",
                    },
                    "operations": [
                        {
                            "operation_id": "write-final-rule",
                            "kind": "WRITE_MATH",
                            "target_kind": "CANVAS_ZONE",
                            "target_ids": ["ZONE:REASONING"],
                            "zone": "REASONING",
                            "persistence": "PERSIST",
                            "evidence_ref": "CHANGING_VALUE",
                            "latex": "n + 5",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    assert _plan(draft) is None


def test_planner_rejects_a_beat_not_present_in_narration(monkeypatch) -> None:
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "bad-voice-anchor",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": 5,
                        "text": "Wrong",
                    },
                    "operations": [
                        {
                            "operation_id": "focus-first-values",
                            "kind": "FOCUS",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                        },
                        {
                            "operation_id": "write-confirmed-observation",
                            "kind": "WRITE_TEXT",
                            "target_kind": "CANVAS_ZONE",
                            "target_ids": ["ZONE:REASONING"],
                            "zone": "REASONING",
                            "persistence": "PERSIST",
                            "evidence_ref": "CHANGING_VALUE",
                            "text": "first numbers",
                            "color_role": "NAVY",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    assert _plan(draft) is None


def test_planner_corrects_a_unique_speech_anchor_offset(monkeypatch) -> None:
    voice = "Look at the first numbers. What do you notice about them?"
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "focus-first-values",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": len(voice) - 2,
                        "text": voice,
                    },
                    "operations": [
                        {
                            "operation_id": "focus-first-values",
                            "kind": "FOCUS",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                        },
                        {
                            "operation_id": "write-confirmed-observation",
                            "kind": "WRITE_TEXT",
                            "target_kind": "CANVAS_ZONE",
                            "target_ids": ["ZONE:REASONING"],
                            "zone": "REASONING",
                            "persistence": "PERSIST",
                            "evidence_ref": "CHANGING_VALUE",
                            "text": "first numbers",
                            "color_role": "NAVY",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    plan = _plan(draft, voice=voice)

    assert plan is not None
    anchor = plan.beats[0].speech_anchor
    assert voice[anchor.start_char:anchor.end_char] == anchor.text


def _direct_explanation_contribution() -> StudentContribution:
    return StudentContribution(
        kind="EXPLANATION_REQUEST",
        assessment="NOT_ASSESSED",
        error_category=None,
        error_description=None,
        identified_difficulty=None,
        learner_question="What does n mean?",
        explained_idea="n represents the changing starting number.",
        generated_support_text=None,
        support_relevance="NOT_NEEDED",
    )


def _single_write_draft(voice: str, text: str, evidence_ref: str) -> CanvasTeachingPlanDraft:
    return CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "write-example",
                    "sequence": 1,
                    "speech_anchor": {
                        "start_char": 0,
                        "end_char": len(voice),
                        "text": voice,
                    },
                    "operations": [
                        {
                            "operation_id": "write-example",
                            "kind": "WRITE_MATH",
                            "target_kind": "CANVAS_ZONE",
                            "target_ids": ["ZONE:REASONING"],
                            "zone": "REASONING",
                            "persistence": "PERSIST",
                            "evidence_ref": evidence_ref,
                            "text": text,
                        }
                    ],
                }
            ]
        }
    )


def test_planner_allows_a_spoken_direct_explanation_example(monkeypatch) -> None:
    voice = "n is the starting number. n equals 3, so 3 plus 5 is one example."
    draft = _single_write_draft(voice, "n = 3 → 3 + 5", "DIRECT_EXPLANATION")
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    plan = _plan(draft, _tutor(_direct_explanation_contribution()), voice)

    assert plan is not None
    assert plan.teaching_mode == "DIRECT_EXPLANATION"


def test_planner_rejects_a_direct_explanation_that_writes_the_final_rule(monkeypatch) -> None:
    voice = "n is the starting number, and plus 5 stays fixed."
    draft = _single_write_draft(voice, "n + 5", "DIRECT_EXPLANATION")
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    assert _plan(draft, _tutor(_direct_explanation_contribution()), voice) is None


def test_planner_rejects_main_canvas_writing_for_visual_support(monkeypatch) -> None:
    voice = "Look at the plus 5 terms."
    draft = _single_write_draft(voice, "plus 5 stays fixed", "FIXED_VALUE")
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    assert _plan(draft, voice=voice, active_support_level="VISUAL_CUE") is None


def test_planner_suppresses_main_canvas_output_for_parallel_example(monkeypatch) -> None:
    parallel_action = TutorCanvasAction(
        action_id="parallel:1",
        type="SHOW_PARALLEL",
        target_kind="TUTOR_ANCHOR",
        target_object_id="TUTOR_ANCHOR:PARALLEL:1",
        confirmed_component_id=None,
        text="Look at a similar example.",
        source_id="parallel-example",
        answer_reveal_allowed=False,
        rescue_id="parallel-example",
        step_index=1,
        total_steps=2,
        presentation_mode="PARALLEL",
        return_target_object_id="Q1:QTOKEN:1",
    )
    draft = CanvasTeachingPlanDraft.model_validate(
        {
            "beats": [
                {
                    "beat_id": "focus-original-question",
                    "sequence": 1,
                    "speech_anchor": {"start_char": 0, "end_char": 5, "text": "Those"},
                    "operations": [
                        {
                            "operation_id": "focus-original-question",
                            "kind": "FOCUS",
                            "target_kind": "QUESTION_ANCHOR",
                            "target_ids": ["Q1:QTOKEN:1"],
                            "zone": "QUESTION",
                            "persistence": "PULSE",
                        }
                    ],
                }
            ]
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    tutor = _tutor().model_copy(update={"tutor_canvas_actions": [parallel_action]})

    assert _plan(draft, tutor=tutor) is None


def test_planner_allows_a_spoken_current_tutor_solved_step(monkeypatch) -> None:
    voice = "Circle 3, then write changing starting number."
    tutor_solved_action = TutorCanvasAction(
        action_id="solved:1",
        type="TUTOR_SOLVED_STEP",
        target_kind="TUTOR_ANCHOR",
        target_object_id="TUTOR_ANCHOR:SOLVED:1",
        confirmed_component_id=None,
        text="Circle 3, then write changing starting number.",
        source_id="tutor-solved",
        answer_reveal_allowed=False,
        rescue_id="tutor-solved",
        step_index=1,
        total_steps=2,
        presentation_mode="TUTOR_SOLVED",
        return_target_object_id="Q1:QTOKEN:1",
    )
    draft = _single_write_draft(voice, "changing starting number", "UNUSED")
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: FakeCanvasTeachingClient(draft),
    )

    tutor = _tutor().model_copy(update={"tutor_canvas_actions": [tutor_solved_action]})
    plan = _plan(draft, tutor=tutor, voice=voice)

    assert plan is not None
    assert plan.teaching_mode == "TUTOR_SOLVED"


def test_planner_writes_a_confirmed_notation_statement_without_openai(monkeypatch) -> None:
    question = "Decode pq and r² without calculating."
    anchors = question_text_tokens("Q-NOTATION", question)
    pq_anchor = next(anchor for anchor in anchors if anchor.text == "pq")
    tutor = _tutor().model_copy(
        update={
            "tutor_message_voice": "Yes — pq means p multiplied by q. What does r² mean?",
            "guided_teaching_state": GuidedTeachingState(
                question_id="Q-NOTATION",
                objective_component_ids=["JUXTAPOSITION", "EXPONENT"],
                confirmed_component_ids=["JUXTAPOSITION"],
                missing_component_ids=["EXPONENT"],
                active_component_id="EXPONENT",
                last_tutor_question_type="COMPONENT",
                selected_option_id=None,
                awaiting_response=True,
                last_turn_evidence=[
                    GuidedEvidenceClaim(
                        concept_id="JUXTAPOSITION",
                        status="DEMONSTRATED",
                        source="TEXT",
                    )
                ],
            ),
            "generated_question_rubric": GeneratedQuestionRubric(
                question_id="Q-NOTATION",
                required_concepts=[
                    GeneratedConcept(
                        concept_id="JUXTAPOSITION",
                        description="pq means p multiplied by q",
                        required=True,
                    )
                ],
                completion_rule="ALL_REQUIRED_CONCEPTS",
                cache_key="notation",
                prompt_version="1.0",
            ),
            "tutor_canvas_actions": [
                TutorCanvasAction(
                    action_id="TURN-NOTATION:1:HIGHLIGHT",
                    type="HIGHLIGHT",
                    target_kind="QUESTION_ANCHOR",
                    target_object_id=pq_anchor.token_id,
                    confirmed_component_id="JUXTAPOSITION",
                    text=None,
                    source_id=None,
                    answer_reveal_allowed=False,
                )
            ],
        }
    )
    monkeypatch.setattr(canvas_teaching_planner, "load_classifier_rules", _enabled_rules)
    monkeypatch.setattr(
        canvas_teaching_planner,
        "build_openai_ai_engine_client",
        lambda _: pytest.fail("confirmed generic scenes must not call OpenAI"),
    )

    plan = canvas_teaching_planner.plan_canvas_teaching(
        question_id="Q-NOTATION",
        question=question,
        source_turn_id="TURN-NOTATION",
        tutor_turn_id="TUTOR-NOTATION",
        scene_revision=1,
        tutor_message_voice=tutor.tutor_message_voice,
        tutor=tutor,
        question_anchors=anchors,
        student_response="p multiplied by q",
        canonical_answer="p × q; r × r",
        active_support_level=None,
        current_unresolved_component_id="EXPONENT",
    )

    assert plan is not None
    assert [(operation.kind, operation.scene_slot) for operation in plan.beats[0].operations] == [
        ("HIGHLIGHT", None),
        ("WRITE_TEXT", "generic_confirmation:JUXTAPOSITION"),
    ]
    assert plan.beats[0].operations[1].text == "pq means p multiplied by q."
