"""Topic-wise attempt history, read back from the Student Model service.

Phase 4 needs the whole topic journey, not just the live session: which
Phase 3 attempts were wrong, what the student wrote, and the question content
needed to explain it. The Student Model service is authoritative for all of
it — this repo only reads and interprets.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DetectedErrorRecord(BaseModel):
    error_code: str
    # The service omits this when an error isn't tied to a specific skill —
    # not missing data, a real case. See phase4_context_builder for how a
    # null value is handled when building a replay item.
    micro_skill_id: str | None = None


class WorkArtifactRef(BaseModel):
    """The stored work for one attempt, as returned with its history.

    Per spec 5.7 the artifact reference travels with the Phase 3 submission
    event, so Phase 4 reads it here rather than from live session state.
    """

    artifact_id: str
    pdf_url: str
    page_count: int


class TopicAttemptRecord(BaseModel):
    attempt_id: str
    question_id: str
    # The service omits this for some attempts (see phase4_context_builder
    # for how a null value is handled when building a replay item).
    question_usage_id: str | None = None
    phase: str
    evaluation: Literal["CORRECT", "INCORRECT", "WRONG"]
    # True once the student answers this unaided; drives improvement evidence.
    independent_success: bool | None = None
    # True when this question was served to replace an earlier wrong one.
    fresh_question_replacement: bool = False
    hint_used: bool = False
    student_response: str | None = None
    attempted_at: str
    # Question content, required to build a replay item. Held by the Student
    # Model service, which stores the full question payloads it served.
    question_text: str = ""
    canonical_answer: str = ""
    answer_steps: list[str] = Field(default_factory=list)
    detected_errors: list[DetectedErrorRecord] = Field(default_factory=list)
    linked_misconceptions: list[str] = Field(default_factory=list)
    # Absent for attempts made before work artifacts existed.
    work_artifact: WorkArtifactRef | None = None

    @property
    def is_wrong(self) -> bool:
        return self.evaluation in {"INCORRECT", "WRONG"}


class TopicEventHistoryResponse(BaseModel):
    topic_id: str
    student_id: str
    topic_info: dict[str, object] = Field(default_factory=dict)
    whole_topic_evidence: dict[str, object] = Field(default_factory=dict)
    attempts: list[TopicAttemptRecord] = Field(default_factory=list)
