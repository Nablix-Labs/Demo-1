from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, model_validator

from app.ai_engine.schemas import (
    ErrorType,
    EvaluationCategory,
    HintLevel,
    LearningPhase,
    StrictSchema,
)


InteractionMode = Literal["TEXT", "VOICE", "CANVAS"]
MasteryStatus = Literal["NOT_STARTED", "EMERGING", "DEVELOPING", "SECURE", "MASTERED"]
CallToAction = Literal["NEXT_TOPIC", "CONTINUE_PRACTICE", "NONE"]


def validate_iso_timestamp(value: str) -> str:
    try:
        parsed_value: datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must use ISO 8601 format") from error
    if parsed_value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value


IsoTimestamp = Annotated[str, AfterValidator(validate_iso_timestamp)]


class SessionPerformance(StrictSchema):
    total_attempts: int = Field(ge=0)
    correct_attempts: int = Field(ge=0)
    incorrect_attempts: int = Field(ge=0)
    hints_used: int = Field(ge=0)
    hint_levels_used: list[HintLevel]
    canvas_submissions: int = Field(ge=0)
    rescue_mode_activations: int = Field(ge=0)
    long_pressure_events: int = Field(ge=0)
    voice_fallback_events: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_attempt_totals(self) -> "SessionPerformance":
        if self.correct_attempts + self.incorrect_attempts != self.total_attempts:
            raise ValueError(
                "correct_attempts and incorrect_attempts must add up to total_attempts"
            )
        if len(self.hint_levels_used) != self.hints_used:
            raise ValueError("hint_levels_used length must match hints_used")
        return self


class QuestionAttempt(StrictSchema):
    question_id: str = Field(min_length=1)
    phase: LearningPhase
    attempt_number: int = Field(ge=1)
    evaluation: EvaluationCategory
    error_type: ErrorType | None
    hint_level_used: HintLevel | None
    independent_success: StrictBool
    canvas_submitted: StrictBool
    canvas_first_error_step: int | None = Field(ge=1)
    canvas_first_error_type: ErrorType | None
    successful_step_descriptions: list[str]
    error_description: str | None
    rescue_activated: StrictBool

    @model_validator(mode="after")
    def validate_attempt_evidence(self) -> "QuestionAttempt":
        if self.evaluation == "CORRECT" and self.error_type is not None:
            raise ValueError("error_type must be null for a correct attempt")
        if self.canvas_submitted is False and (
            self.canvas_first_error_step is not None
            or self.canvas_first_error_type is not None
        ):
            raise ValueError("canvas error fields require canvas_submitted=true")
        if any(description.strip() == "" for description in self.successful_step_descriptions):
            raise ValueError("successful_step_descriptions cannot contain blank values")
        if self.error_description is not None and self.error_description.strip() == "":
            raise ValueError("error_description cannot be blank")
        return self


class CanvasReviewHistory(StrictSchema):
    canvas_snapshot_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    overall_evaluation: EvaluationCategory
    first_error_step: int | None = Field(ge=1)
    first_error_type: ErrorType | None


class PhaseTransition(StrictSchema):
    from_phase: LearningPhase
    to_phase: LearningPhase
    timestamp: IsoTimestamp


class SessionSummary(StrictSchema):
    session_id: str = Field(pattern=r"^SESSION\d{3}$")
    student_id: str = Field(pattern=r"^ST\d{3}$")
    concept_id: str = Field(min_length=1)
    session_date: IsoTimestamp
    session_duration_seconds: int = Field(ge=0)
    interaction_mode: InteractionMode
    phase_4_entry_reason: Literal["normal_review"]
    phases_completed: list[LearningPhase]
    session_performance: SessionPerformance
    per_question_history: list[QuestionAttempt] = Field(min_length=1)
    canvas_feedback_history: list[CanvasReviewHistory]
    phase_transitions: list[PhaseTransition]


class StudentModelReview(StrictSchema):
    mastery_status: MasteryStatus
    error_counts: dict[ErrorType, int]
    dominant_error_type: ErrorType | None
    hint_dependency_score: float = Field(ge=0.0, le=1.0)
    error_confirmed_pattern: StrictBool
    recommended_entry_phase: LearningPhase
    next_concept_recommendation: str | None

    @model_validator(mode="after")
    def validate_error_evidence(self) -> "StudentModelReview":
        if any(count < 0 for count in self.error_counts.values()):
            raise ValueError("error_counts cannot contain negative values")
        if (
            self.dominant_error_type is not None
            and self.dominant_error_type not in self.error_counts
        ):
            raise ValueError("dominant_error_type must be present in error_counts")
        if self.error_confirmed_pattern and self.dominant_error_type is None:
            raise ValueError("a confirmed pattern requires dominant_error_type")
        return self


class SessionReviewRequest(StrictSchema):
    session_summary: SessionSummary
    student_model: StudentModelReview


class FiveCategorySummary(StrictSchema):
    category_1_strength: str = Field(min_length=1)
    category_2_first_error: str | None
    category_3_pattern: str | None
    category_4_next_practice: str = Field(min_length=1)
    category_5_mastery: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_optional_categories(self) -> "FiveCategorySummary":
        optional_values: tuple[str | None, str | None] = (
            self.category_2_first_error,
            self.category_3_pattern,
        )
        if any(value is not None and value.strip() == "" for value in optional_values):
            raise ValueError("optional review categories cannot be blank")
        return self


class GeneratedSessionReview(StrictSchema):
    five_category_summary: FiveCategorySummary
    student_facing_summary: str = Field(min_length=1)
    b6_hook: str | None

    @model_validator(mode="after")
    def validate_b6_hook(self) -> "GeneratedSessionReview":
        if self.b6_hook is not None and self.b6_hook.strip() == "":
            raise ValueError("b6_hook cannot be blank")
        return self


class SessionReviewResponse(GeneratedSessionReview):
    call_to_action: CallToAction
    voice_delivery_order: list[str]
    answer_reveal_allowed: Literal[False]
    guardrail_passed: Literal[True]
