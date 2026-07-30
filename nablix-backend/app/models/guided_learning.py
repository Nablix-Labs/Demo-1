from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


GuidedStudentState = Literal["CORRECT", "PARTIAL", "WRONG", "STUCK", "UNCLEAR"]


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


class GuidedEvaluation(GuidedLearningModel):
    student_state: GuidedStudentState
    newly_confirmed_concept_ids: list[str]
    preserved_concept_ids: list[str]
    contradicted_concept_ids: list[str]
    missing_concept_ids: list[str]
    selected_error_code: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    next_objective: ActiveTeachingObjective | None
    tutor_message: str
    tutor_message_voice: str
