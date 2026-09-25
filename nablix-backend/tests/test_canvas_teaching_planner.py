from app.ai_engine.classifier_config import load_classifier_rules
from app.models.adapters import TutorResult
from app.models.canvas_teaching import CanvasTeachingPlanDraft
from app.models.guided_learning import (
    GuidedEvidenceClaim,
    GuidedTeachingState,
    StudentContribution,
    TutorCanvasAction,
)
from app.models.question_anchor import QuestionTextAnchor
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

    plan = _plan(draft)

    assert plan is not None
    assert plan.plan_id == "Q1:TURN-1:canvas-teaching"
    assert plan.beats[0].operations[0].target_ids == ["Q1:QTOKEN:1"]


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
