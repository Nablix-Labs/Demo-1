"""
Pydantic models for AD-401 -- Visual Cue Retrieval Engine.

Request/response schemas for POST /visual-cue/retrieve.
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class Difficulty(str, Enum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class VisualCueRetrieveRequest(BaseModel):
    """Request body for POST /visual-cue/retrieve.

    The AI tutor sends this when it decides a visual aid would help.
    It tells us what concept the student is working on, what type
    of error they made, and the difficulty level.
    """
    concept_id: str
    error_type: str
    difficulty: Difficulty = Difficulty.FOUNDATION
    exclude_content_ids: list[str] = Field(default_factory=list)


class VisualCueRetrieveResponse(BaseModel):
    """Response body for POST /visual-cue/retrieve.

    Returns the visual cue description that Manav's frontend
    will render. The visual_cue_type tells the frontend what
    kind of visual component to use.
    """
    content_id: str
    concept_id: str
    visual_cue_type: str
    text: str
    voice_text: Optional[str] = None
    error_type: str
    difficulty: str
    topic: str
    subtopic: str
    relevance_score: float
    approval_status: str


class VisualCueNotFoundResponse(BaseModel):
    """Returned when no visual cue matches the request."""
    detail: str
    concept_id: str
    error_type: str
    difficulty: str
