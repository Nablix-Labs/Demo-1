from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.student_model_session import WorkedExample


TeachBackAction = Literal[
    "ASK_TEACH_BACK", "DISCUSS_AND_CLARIFY", "ASK_REEXPLANATION",
    "NEXT_MICRO_SKILL", "MOVE_TO_PHASE_2", "RETURN_TO_ORIENTATION",
]


class TeachBackEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    understanding_status: Literal["UNDERSTOOD", "MISCONCEPTION"] | None
    misconception_detected: bool
    error_code: str | None
    unmapped_misconception_description: str | None

    @model_validator(mode="after")
    def validate_misconception(self) -> "TeachBackEvaluation":
        detail = bool((self.error_code or "").strip() or (self.unmapped_misconception_description or "").strip())
        if self.understanding_status == "MISCONCEPTION":
            if not self.misconception_detected or not detail:
                raise ValueError("MISCONCEPTION requires a description or known error code.")
        elif self.misconception_detected or detail:
            raise ValueError("Only a MISCONCEPTION verdict can report a misconception.")
        return self


class TeachBackReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation: TeachBackEvaluation
    tutor_message: str = Field(min_length=1)
    tutor_message_voice: str = Field(min_length=1)
    next_action: TeachBackAction


class TeachBackMisconception(BaseModel):
    error_code: str
    description: str


class TeachBackDiagnosticSource(BaseModel):
    question_id: str
    question_usage_id: str | None


class TeachBackTarget(BaseModel):
    micro_skill_id: str
    source_diagnostic_questions: list[TeachBackDiagnosticSource]
    micro_skill_definition: str = Field(min_length=1)
    expected_concept: str = Field(min_length=1)
    known_misconceptions: list[TeachBackMisconception]


class TeachBackStoredReply(BaseModel):
    tutor_response: str
    tutor_response_voice: str | None = None
    tutor_next_action: TeachBackAction
    turn_id: str


class TeachBackState(BaseModel):
    teach_back_id: str
    status: Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]
    target_micro_skill_ids: list[str] = Field(min_length=1)
    completed_micro_skill_ids: list[str]
    current_micro_skill_id: str | None
    conversation_mode: TeachBackAction
    failed_explanation_count: int | None = Field(default=None, ge=0)
    last_tutor_response: TeachBackStoredReply | None = None

    @model_validator(mode="after")
    def validate_skill_progress(self) -> "TeachBackState":
        targets = set(self.target_micro_skill_ids)
        completed = set(self.completed_micro_skill_ids)
        if len(targets) != len(self.target_micro_skill_ids) or not completed.issubset(targets):
            raise ValueError("Teach-Back progress must contain unique, valid target skills.")
        if self.current_micro_skill_id is not None and (
            self.current_micro_skill_id not in targets or self.current_micro_skill_id in completed
        ):
            raise ValueError("The current Teach-Back skill must be an unfinished target.")
        return self


class TeachBackTeachingSummary(BaseModel):
    micro_skill_id: str
    skill_name: str
    summary: str


class TeachBackCompletedContent(BaseModel):
    orientation_video_id: str | None
    worked_example_ids: list[str]


class TeachBackPhase1Context(BaseModel):
    taught_micro_skill_ids: list[str]
    completed_content_ids: TeachBackCompletedContent
    teaching_summary: list[TeachBackTeachingSummary]


class TeachBackWorkedExampleContext(BaseModel):
    worked_examples: list[WorkedExample]


class TeachBackPayload(BaseModel):
    teach_back_id: str
    state: TeachBackState
    topic_id: str | None = None
    targets: list[TeachBackTarget]
    phase1_context: TeachBackPhase1Context
    worked_example_context: TeachBackWorkedExampleContext
