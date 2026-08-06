from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


GuidedStudentState = Literal["CORRECT", "PARTIAL", "WRONG", "STUCK", "UNCLEAR"]
EvaluationReasonCode = Literal[
    "ALL_REQUIRED_COMPONENTS_CONFIRMED",
    "REQUIRED_COMPONENTS_MISSING",
    "RESPONSE_INCORRECT",
    "STUDENT_STUCK",
    "RESPONSE_UNCLEAR",
    "EXPLAIN_AGAIN_REEXPRESSION",
]
WrongSupportReasonCode = Literal[
    "WRONG_1_HINT",
    "WRONG_2_HINT",
    "WRONG_3_VISUAL_CUE",
    "WRONG_4_INTERVENTION",
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


class EvaluationReasonCode(str, Enum):
    ALL_REQUIRED_COMPONENTS_CONFIRMED = "ALL_REQUIRED_COMPONENTS_CONFIRMED"
    REQUIRED_COMPONENTS_MISSING = "REQUIRED_COMPONENTS_MISSING"
    RESPONSE_INCORRECT = "RESPONSE_INCORRECT"
    STUDENT_STUCK = "STUDENT_STUCK"
    RESPONSE_UNCLEAR = "RESPONSE_UNCLEAR"


class WrongEscalationCode(str, Enum):
    WRONG_1_HINT = "WRONG_1_HINT"
    WRONG_2_HINT = "WRONG_2_HINT"
    WRONG_3_VISUAL_CUE = "WRONG_3_VISUAL_CUE"
    WRONG_4_INTERVENTION = "WRONG_4_INTERVENTION"


class GuidedLearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


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


class ActiveScaffold(GuidedLearningModel):
    scaffold_id: str
    current_step_id: str
    step_number: int = Field(ge=1)
    total_steps: int = Field(ge=1)
    step_text: str
    step_voice: str | None


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
