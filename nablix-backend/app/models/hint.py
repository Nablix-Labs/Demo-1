from pydantic import BaseModel

from app.models.fields import ConceptId, Phase, QuestionId, SessionId, StudentId


class HintRequest(BaseModel):
    """Validated request for a tutor hint."""

    session_id: SessionId
    student_id: StudentId
    current_phase: Phase
    current_hint_count: int
    concept_id: ConceptId
    question_id: QuestionId


class HintResponse(BaseModel):
    """Short hint response shaped from the tutor pipeline."""

    session_id: str
    student_id: str
    hint_level: int
    hint: str
    response_strategy: str
    answer_reveal_allowed: bool
