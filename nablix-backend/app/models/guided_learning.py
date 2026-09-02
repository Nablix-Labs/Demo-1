from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.models.canvas_memory import CanvasEvent
from app.models.question_anchor import QuestionTextAnchor


GuidedStudentState = Literal["CORRECT", "PARTIAL", "WRONG", "STUCK", "UNCLEAR"]
GuidedEvidenceStatus = Literal["DEMONSTRATED", "CONTRADICTED"]
GuidedEvidenceSource = Literal["TEXT", "VOICE", "OCR", "CANVAS", "STRUCTURED"]
GuidedPromptType = Literal[
    "COMPONENT",
    "OPTION_COMPARISON",
    "SOURCE_CORRECTION",
    "DEFENCE",
]
ComponentEvidenceStatus = Literal[
    "DEMONSTRATED",
    "CONTRADICTED",
    "NOT_DEMONSTRATED",
]
GuidedRoutingReasonCode = Literal[
    "GUIDED_IN_PROGRESS",
    "GUIDED_HINT_REQUIRED",
    "GUIDED_VISUAL_SUPPORT_REQUIRED",
    "GUIDED_SCAFFOLD_REQUIRED",
    "GUIDED_COMPLETED",
    "GUIDED_PHASE_COMPLETED",
    "PARALLEL_EXAMPLE_REQUIRED",
]
TutorCanvasActionType = Literal[
    "HIGHLIGHT",
    "GROUP",
    "ARROW",
    "INSERT_MATH",
    "INSERT_LABEL",
    "FOCUS",
    "SHOW_CUE",
    "OPEN_SCAFFOLD_STEP",
    "SHOW_PARALLEL",
    "TUTOR_SOLVED_STEP",
]
TutorCanvasTargetKind = Literal[
    "QUESTION_ANCHOR",
    "QUESTION_OPTION",
    "CANVAS_OBJECT",
    "STUDENT_ATTEMPT",
    "TUTOR_ANCHOR",
    "WRITE_AREA",
]


class EvaluationReasonCode(str, Enum):
    ALL_REQUIRED_COMPONENTS_CONFIRMED = "ALL_REQUIRED_COMPONENTS_CONFIRMED"
    REQUIRED_COMPONENTS_MISSING = "REQUIRED_COMPONENTS_MISSING"
    RESPONSE_INCORRECT = "RESPONSE_INCORRECT"
    STUDENT_STUCK = "STUDENT_STUCK"
    RESPONSE_UNCLEAR = "RESPONSE_UNCLEAR"
    EXPLAIN_AGAIN_REEXPRESSION = "EXPLAIN_AGAIN_REEXPRESSION"


class WrongEscalationCode(str, Enum):
    WRONG_1_HINT = "WRONG_1_HINT"
    WRONG_2_HINT = "WRONG_2_HINT"
    WRONG_3_VISUAL_CUE = "WRONG_3_VISUAL_CUE"
    WRONG_4_INTERVENTION = "WRONG_4_INTERVENTION"


class GuidedLearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GeneratedConcept(GuidedLearningModel):
    concept_id: str
    description: str
    required: StrictBool


class GeneratedQuestionRubric(GuidedLearningModel):
    question_id: str
    required_concepts: list[GeneratedConcept]
    completion_rule: Literal["ALL_REQUIRED_CONCEPTS"]
    cache_key: str
    prompt_version: str


class ActiveTeachingObjective(GuidedLearningModel):
    objective_type: str
    target_concept_ids: list[str]
    confirmed_concept_ids: list[str]
    missing_concept_ids: list[str]


class GuidedEvidenceClaim(GuidedLearningModel):
    """One concept claim with the channel that demonstrated it."""

    concept_id: str
    status: GuidedEvidenceStatus
    source: GuidedEvidenceSource


class GuidedTeachingState(GuidedLearningModel):
    """Persisted controller state for one Guided Learning question.

    The LLM may interpret a learner's wording, but this state is the source of
    truth for which sub-question is currently awaiting an answer.
    """

    question_id: str
    objective_component_ids: list[str]
    confirmed_component_ids: list[str]
    missing_component_ids: list[str]
    active_component_id: str | None
    last_tutor_question_type: GuidedPromptType
    selected_option_id: str | None
    selected_option_text: str | None = None
    typed_option_id: str | None = None
    typed_option_text: str | None = None
    awaiting_response: StrictBool
    active_step_id: str | None = None
    teaching_step_ids: list[str] = Field(default_factory=list)
    answer_step_ids: list[str] = Field(default_factory=list)
    completed_step_ids: list[str] = Field(default_factory=list)
    current_step_index: int | None = Field(default=None, ge=0)
    affect_state: Literal["NORMAL", "DISTRESS", "FRUSTRATED", "GENTLE_RETURN"] = "NORMAL"
    last_reasoning_probe: str | None = None
    demonstrated_reasoning_ids: list[str] = Field(default_factory=list)
    evidence_ledger: list[GuidedEvidenceClaim] = Field(default_factory=list)
    last_turn_evidence: list[GuidedEvidenceClaim] = Field(default_factory=list)


class GuidedTeachingPlanStep(GuidedLearningModel):
    """One ordered learner-facing focus in a Guided Learning question."""

    step_id: str
    tutor_question: str
    answer_step_id: str | None = None


class GuidedRescueContext(GuidedLearningModel):
    """Authored rescue step selected by orchestration for this tutor turn."""

    rescue_id: str = Field(min_length=1)
    rescue_type: Literal["PARALLEL_EXAMPLE", "TUTOR_SOLVED"]
    source_id: str = Field(min_length=1)
    current_step_index: int = Field(ge=1)
    total_steps: int = Field(ge=1)
    current_step_text: str = Field(min_length=1, max_length=80)
    is_final_step: StrictBool
    approved_answer_reveal: StrictBool
    return_target_object_id: str = Field(min_length=1)
    active_support: Literal["PARALLEL_EXAMPLE", "TUTOR_SOLVED"]
    active_action_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rescue_step(self) -> "GuidedRescueContext":
        if self.rescue_type != self.active_support:
            raise ValueError("rescue_type must match active_support.")
        if self.current_step_index > self.total_steps:
            raise ValueError("current_step_index must not exceed total_steps.")
        if self.is_final_step != (self.current_step_index == self.total_steps):
            raise ValueError("is_final_step must match current_step_index.")
        if self.approved_answer_reveal and (
            self.rescue_type != "TUTOR_SOLVED" or not self.is_final_step
        ):
            raise ValueError(
                "approved_answer_reveal is allowed only for the final Tutor-Solved step."
            )
        return self


class GuidedCanvasEvidence(GuidedLearningModel):
    """Canvas evidence paired with the learner's current turn."""

    snapshot_reference: str | None = None
    ocr_regions: list[dict[str, object]] = Field(default_factory=list)
    spatial_tokens: list[dict[str, object]] = Field(default_factory=list)
    strokes: list[dict[str, object]] = Field(default_factory=list)
    ordered_events: list[CanvasEvent] = Field(default_factory=list)


class GuidedTutorContext(GuidedLearningModel):
    """Authoritative lesson state supplied to the guided-turn evaluator."""

    active_tutor_question: str
    active_step_id: str | None
    ordered_teaching_steps: list[GuidedTeachingPlanStep]
    confirmed_concept_ids: list[str]
    missing_concept_ids: list[str]
    support_state: dict[str, object]
    current_support: dict[str, object] | None
    active_support_content: dict[str, object] | None
    selected_option_id: str | None
    selected_option_text: str | None
    active_canvas_events: list[CanvasEvent]
    canvas_evidence: GuidedCanvasEvidence = Field(default_factory=GuidedCanvasEvidence)
    prior_tutor_response: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    learning_phase: str = "GUIDED_PRACTICE"
    active_question_anchors: list[QuestionTextAnchor]
    current_scaffold_step_number: int
    consecutive_stuck_count: int
    conversation_state_summary: str
    rescue_context: GuidedRescueContext | None = None


class ActiveScaffold(GuidedLearningModel):
    scaffold_id: str
    current_step_id: str
    step_number: int = Field(ge=1)
    total_steps: int = Field(ge=1)
    step_text: str
    step_voice: str | None


class ParallelExample(GuidedLearningModel):
    parallel_example_id: str
    problem: str
    worked_steps: list[str]
    final_answer: str


class TutorSolved(GuidedLearningModel):
    explanation: str
    final_answer: str
    answer_steps: list[str]


class GuidedRescue(GuidedLearningModel):
    rescue_type: Literal["PARALLEL_EXAMPLE", "TUTOR_SOLVED"]
    micro_skill_id: str
    parallel_example: ParallelExample | None
    tutor_solved: TutorSolved | None
    tutor_engine_context: GuidedRescueContext | None = None


def rescue_action_id(rescue_id: str, step_index: int) -> str:
    """The one stable rescue action id, shared by every producer."""

    return f"{rescue_id}:step:{step_index}"


class ActiveGuidedRescue(GuidedLearningModel):
    """Private persisted cursor for server-owned rescue presentation."""

    question_id: str = Field(min_length=1)
    rescue_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    rescue_type: Literal["PARALLEL_EXAMPLE", "TUTOR_SOLVED"]
    steps: list[str] = Field(min_length=1)
    current_step_index: int = Field(default=1, ge=1)
    rendered_action_ids: list[str] = Field(default_factory=list)
    return_target_object_id: str = Field(min_length=1)
    final_reveal_approved: StrictBool = False
    pending_phase3_transition: StrictBool = False

    @model_validator(mode="after")
    def validate_cursor(self) -> "ActiveGuidedRescue":
        if self.current_step_index > len(self.steps):
            raise ValueError("current_step_index must not exceed rescue steps.")
        if any(len(step.strip()) == 0 for step in self.steps):
            raise ValueError("rescue steps must not be empty.")
        return self

    @property
    def current_action_id(self) -> str:
        return rescue_action_id(self.rescue_id, self.current_step_index)

    @property
    def current_target_object_id(self) -> str:
        return f"TUTOR_ANCHOR:RESCUE:{self.rescue_id}:STEP:{self.current_step_index}"

    @property
    def is_final_step(self) -> bool:
        return self.current_step_index == len(self.steps)


class PrerequisiteRepair(GuidedLearningModel):
    prerequisite_micro_skill_ids: list[str]
    reason_code: str


class InactivityPolicy(GuidedLearningModel):
    initial_idle_threshold_ms: int = Field(ge=1)
    cooldown_ms: int = Field(ge=1)
    max_nudges_per_tutor_turn: int = Field(ge=1)
    generated_nudge_rate_limit: int = Field(ge=1)


class NudgeDelivery(GuidedLearningModel):
    interaction_id: str
    status: Literal["GENERATED", "PRESENTED"]
    message: str = Field(min_length=1)


class CanvasPedagogyIntent(GuidedLearningModel):
    """A semantic evaluator suggestion, not a browser drawing command."""

    action_type: TutorCanvasActionType
    target_kind: TutorCanvasTargetKind
    target_object_id: str | None
    confirmed_component_id: str | None
    text: str | None = Field(max_length=80)
    source_id: str | None


class TutorCanvasAction(GuidedLearningModel):
    """Validated Phase 2 action owned visually by the frontend."""

    action_id: str
    type: TutorCanvasActionType
    target_kind: TutorCanvasTargetKind
    target_object_id: str | None
    confirmed_component_id: str | None
    text: str | None = Field(default=None, max_length=80)
    source_id: str | None
    answer_reveal_allowed: StrictBool = False
    rescue_id: str | None = None
    step_index: int | None = Field(default=None, ge=1)
    total_steps: int | None = Field(default=None, ge=1)
    presentation_mode: Literal["PARALLEL", "TUTOR_SOLVED"] | None = None
    return_target_object_id: str | None = None

    @model_validator(mode="after")
    def validate_rescue_action(self) -> "TutorCanvasAction":
        rescue_types = {"SHOW_PARALLEL", "TUTOR_SOLVED_STEP"}
        rescue_fields_present = any(
            value is not None
            for value in (
                self.rescue_id,
                self.step_index,
                self.total_steps,
                self.presentation_mode,
                self.return_target_object_id,
            )
        )
        if self.type not in rescue_types:
            if rescue_fields_present:
                raise ValueError("rescue fields are allowed only on rescue actions.")
            if self.answer_reveal_allowed:
                raise ValueError("only an approved Tutor-Solved step may reveal an answer.")
            return self
        if (
            self.rescue_id is None
            or self.step_index is None
            or self.total_steps is None
            or self.presentation_mode is None
            or self.return_target_object_id is None
            or self.source_id is None
        ):
            raise ValueError("rescue actions require rescue metadata and source_id.")
        if self.step_index > self.total_steps:
            raise ValueError("rescue action step_index must not exceed total_steps.")
        expected_mode = "PARALLEL" if self.type == "SHOW_PARALLEL" else "TUTOR_SOLVED"
        if self.presentation_mode != expected_mode:
            raise ValueError("rescue action presentation_mode does not match type.")
        if self.answer_reveal_allowed and (
            self.type != "TUTOR_SOLVED_STEP" or self.step_index != self.total_steps
        ):
            raise ValueError("only the final Tutor-Solved step may reveal an answer.")
        return self


def inactivity_policy() -> InactivityPolicy:
    return InactivityPolicy(
        initial_idle_threshold_ms=20_000,
        cooldown_ms=30_000,
        max_nudges_per_tutor_turn=2,
        generated_nudge_rate_limit=4,
    )


class GuidedEvaluation(GuidedLearningModel):
    student_state: GuidedStudentState
    newly_confirmed_concept_ids: list[str]
    preserved_concept_ids: list[str]
    contradicted_concept_ids: list[str]
    missing_concept_ids: list[str]
    selected_error_code: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    next_objective: ActiveTeachingObjective | None
    tutor_message: str = Field(min_length=1)
    tutor_message_voice: str = Field(min_length=1)
    write_instruction: str | None = Field(default=None, max_length=160)
    canvas_intentions: list[CanvasPedagogyIntent] = Field(default_factory=list)


class FocusedComponentEvidence(GuidedLearningModel):
    component_id: str = Field(min_length=1)
    status: ComponentEvidenceStatus
    evidence: str | None
    confidence: float = Field(ge=0.0, le=1.0)


class ScaffoldEvaluationContext(GuidedLearningModel):
    scaffold_id: str
    step_id: str
    original_question: str
    canonical_answer: str
    accepted_answers: list[str]
    verification_method: str | None
    step_prompt: str
    expected_response_criterion: str
    completed_step_ids: list[str]


class ScaffoldStepEvaluation(GuidedLearningModel):
    step_satisfied: StrictBool
    original_answer_correct: StrictBool
    demonstrated_fact: str | None
    confidence: float = Field(ge=0.0, le=1.0)
