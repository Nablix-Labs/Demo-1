"""
Pydantic models for AD-402 -- Worked Example Retrieval Engine.

Request/response schemas for POST /worked-example/retrieve.

The request includes the student's current question and answer so we can:
1. Filter out examples that use the same numbers (hard rule)
2. Run the guardrail check to make sure the example doesn't reveal the answer
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Difficulty(str, Enum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class WorkedExampleRetrieveRequest(BaseModel):
    """Request body for POST /worked-example/retrieve.

    The AI tutor sends this when it decides the student needs to see
    a similar problem solved step by step. It includes the student's
    current question and answer so we can make sure the worked example
    uses different numbers and doesn't accidentally give away the answer.
    """
    concept_id: str
    operation_type: str
    current_question: str
    current_answer: str
    difficulty: Difficulty = Difficulty.FOUNDATION
    exclude_content_ids: list[str] = Field(default_factory=list)


class WorkedExampleRetrieveResponse(BaseModel):
    """Response body for POST /worked-example/retrieve.

    Returns the worked example with a step-by-step solution.
    different_numbers_confirmed is always True in the response --
    we only return examples that passed both the different-numbers
    check and the guardrail check.
    """
    content_id: str
    content_type: str = "WORKED_EXAMPLE"
    concept_id: str
    operation_type: str
    example_question: str
    example_answer: str
    text: str
    voice_text: Optional[str] = None
    difficulty: str
    topic: str
    subtopic: str
    different_numbers_confirmed: bool = True
    relevance_score: float
    approval_status: str


class WorkedExampleNotFoundResponse(BaseModel):
    """Returned when no worked example matches the request."""
    detail: str
    concept_id: str
    operation_type: str
    difficulty: str
