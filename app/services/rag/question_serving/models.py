"""
Pydantic models for AD-300 — Question Serving.

Request/response schemas for POST /question/next.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Phase(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    CONCEPT_ORIENTATION = "CONCEPT_ORIENTATION"
    GUIDED_PRACTICE = "GUIDED_PRACTICE"
    INDEPENDENT_PRACTICE = "INDEPENDENT_PRACTICE"
    REVIEW = "REVIEW"


class Difficulty(str, Enum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class QuestionNextRequest(BaseModel):
    """Request body for POST /question/next."""
    concept_id: str
    phase: Phase
    difficulty: Difficulty = Difficulty.FOUNDATION
    previously_seen_ids: list[str] = Field(default_factory=list)
    student_id: Optional[str] = None


class QuestionNextResponse(BaseModel):
    """Response body for POST /question/next."""
    question_id: str
    question_text: str
    correct_answer: str
    difficulty: str
    phase: str
    concept_id: str
    topic: str
    subtopic: str
    voice_text: Optional[str] = None


class QuestionNotFoundResponse(BaseModel):
    """Returned when no unseen questions are available."""
    detail: str
    concept_id: str
    phase: str
    difficulty: str
    total_seen: int


# --- AD-400: Diagnostic Question Bank ---

class DiagnosticQuestionRequest(BaseModel):
    """Request body for POST /diagnostic/question.

    No phase field needed -- diagnostic questions are always DIAGNOSTIC phase.
    The caller just says which concept and difficulty they want.
    """
    concept_id: str
    difficulty: Difficulty = Difficulty.FOUNDATION
    previously_seen_ids: list[str] = Field(default_factory=list)
    student_id: Optional[str] = None


class DiagnosticQuestionResponse(BaseModel):
    """Response body for POST /diagnostic/question.

    Same as QuestionNextResponse but adds diagnostic_purpose
    and expected_method -- the extra fields that tell the AI engine
    WHY this question is being asked and HOW the student should solve it.
    """
    question_id: str
    question_text: str
    correct_answer: str
    difficulty: str
    phase: str
    concept_id: str
    topic: str
    subtopic: str
    voice_text: Optional[str] = None
    diagnostic_purpose: Optional[str] = None
    expected_method: Optional[str] = None
