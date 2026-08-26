from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.ai_engine.schemas import StrictSchema


Phase4Evaluation = Literal["INCORRECT", "WRONG"]


class TopicInfo(StrictSchema):
    title: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    learning_goals: list[str] = Field(min_length=1)


class TopicOutcome(StrictSchema):
    mastery_status: str = Field(min_length=1)
    recommended_next_action: str = Field(min_length=1)


class WorkArtifact(StrictSchema):
    artifact_id: str = Field(min_length=1)
    pdf_url: str = Field(min_length=1)
    page_count: int = Field(ge=1)


class DetectedError(StrictSchema):
    error_code: str = Field(min_length=1)
    micro_skill_id: str = Field(min_length=1)


class ReplayItem(StrictSchema):
    review_item_id: str = Field(min_length=1)
    phase: Literal["PHASE_3_INDEPENDENT_PRACTICE"]
    evaluation: Phase4Evaluation
    question_id: str = Field(min_length=1)
    question_usage_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    question_text: str = Field(min_length=1)
    student_answer: str | None = None
    ocr_text: str | None = None
    work_artifact: WorkArtifact
    detected_errors: list[DetectedError] = Field(min_length=1)
    linked_misconceptions: list[str]
    canonical_answer: str = Field(min_length=1)
    answer_steps: list[str] = Field(min_length=1)


class FinalIndependentResult(StrictSchema):
    question_id: str = Field(min_length=1)
    evaluation: str = Field(min_length=1)
    independent: bool


class WholeTopicEvidence(StrictSchema):
    strong_micro_skill_ids: list[str]
    developing_micro_skill_ids: list[str]
    root_gap_micro_skill_ids: list[str]
    # Nested by micro-skill, which is what "cluster" means here and what Student
    # Model actually emits (merge_error_counts in app/services/topic_summary.py
    # builds {micro_skill_id: {error_code: count}}). Its flat {error_code: count}
    # counter is a different field, top_error_codes, which the event-history
    # response does not carry.
    error_cluster_counts: dict[str, dict[str, int]]
    # Flat, unlike error_cluster_counts above. Verified against
    # merge_misconception_counts, which keys straight off misconception_id.
    misconception_recurrence_counts: dict[str, int]
    hint_count: int = Field(ge=0)
    fresh_question_required: bool
    phase_2_repair_required: bool
    final_independent_results: list[FinalIndependentResult]

    @model_validator(mode="after")
    def validate_non_negative_counts(self) -> "WholeTopicEvidence":
        if any(
            count < 0
            for cluster in self.error_cluster_counts.values()
            for count in cluster.values()
        ):
            raise ValueError("error_cluster_counts cannot contain negative values")
        if any(count < 0 for count in self.misconception_recurrence_counts.values()):
            raise ValueError("misconception_recurrence_counts cannot contain negative values")
        return self


class Phase4ReviewRequest(StrictSchema):
    topic_info: TopicInfo
    topic_outcome: TopicOutcome
    replay_items: list[ReplayItem]
    whole_topic_evidence: WholeTopicEvidence

    @model_validator(mode="after")
    def validate_unique_replay_items(self) -> "Phase4ReviewRequest":
        review_item_ids = [item.review_item_id for item in self.replay_items]
        if len(set(review_item_ids)) != len(review_item_ids):
            raise ValueError("replay_items must have unique review_item_id values")
        # (question_usage_id, attempt_id), not attempt_id alone. Student Model
        # builds attempt_id as f"ATTEMPT-{attempt_sequence:03d}" and the sequence
        # restarts on each question, so two different attempts on two different
        # questions legitimately share one. The pair is what identifies an
        # attempt, and keeping the check on the pair still stops two attempts on
        # the SAME question from being conflated in a replay.
        attempts = [(item.question_usage_id, item.attempt_id) for item in self.replay_items]
        if len(set(attempts)) != len(attempts):
            raise ValueError(
                "replay_items must have unique (question_usage_id, attempt_id) pairs"
            )
        return self


class FirstError(StrictSchema):
    summary: str = Field(min_length=1)
    student_page_no: int | None = Field(default=None, ge=1)


class TutorReplayStep(StrictSchema):
    sequence_no: int = Field(ge=1)
    narration: str = Field(min_length=1)
    tutor_write: str = Field(min_length=1)


class TutorReplay(StrictSchema):
    review_item_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    first_error: FirstError
    replay_steps: list[TutorReplayStep] = Field(min_length=1)
    # Forwarded from the request after generation, never asked of the model:
    # both are already known deterministically (ReplayItem.question_text /
    # .work_artifact), so there is nothing for the LLM to get wrong here.
    question_text: str | None = None
    work_artifact: WorkArtifact | None = None

    @model_validator(mode="after")
    def validate_step_order(self) -> "TutorReplay":
        expected = list(range(1, len(self.replay_steps) + 1))
        if [step.sequence_no for step in self.replay_steps] != expected:
            raise ValueError("replay_steps must be ordered consecutively from 1")
        return self


class StudentInsights(StrictSchema):
    strength_summary: str = Field(min_length=1)
    development_summary: str = Field(min_length=1)
    learning_pattern_summary: str | None = None
    recent_improvement_summary: str | None = None
    next_practice_focus: str = Field(min_length=1)
    personalised_notes: list[str] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def validate_notes(self) -> "StudentInsights":
        if len({note.strip().lower() for note in self.personalised_notes}) != len(self.personalised_notes):
            raise ValueError("personalised_notes must not contain duplicates")
        return self


class QuestionJourneyItem(StrictSchema):
    """One Phase 3 attempt, for the review rail's full journey (not just corrections)."""

    question_id: str = Field(min_length=1)
    evaluation: str = Field(min_length=1)
    hint_used: bool
    independent_success: bool | None = None
    attempted_at: str = Field(min_length=1)


class Phase4ReviewResponse(StrictSchema):
    tutor_replays: list[TutorReplay]
    student_insights: StudentInsights
    # Forwarded from the request after generation, never asked of the model —
    # both come straight from data the session already holds (see
    # generate_phase4_review_for in session_service.py).
    topic_outcome: TopicOutcome | None = None
    question_journey: list[QuestionJourneyItem] | None = None
