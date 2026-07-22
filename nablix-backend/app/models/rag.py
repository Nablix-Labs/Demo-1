from typing import Literal

from pydantic import BaseModel, Field, model_validator


RAGContentType = Literal[
    "CONCEPT_EXPLANATION",
    "PREREQUISITE",
    "MISCONCEPTION",
    "HINT",
    "SCAFFOLD_STEP",
    "REFLECTION_QUESTION",
    "VISUAL_CUE",
    "WORKED_EXAMPLE",
    "DIAGNOSTIC_QUESTION",
    "MASTERY_CHECK",
    "PRACTICE_QUESTION",
]
RAGDifficulty = Literal["FOUNDATION", "INTERMEDIATE", "ADVANCED"]
RAGInputSource = Literal["TEXT", "VOICE", "CANVAS"]

_ERROR_SPECIFIC_CONTENT: frozenset[str] = frozenset(
    {"HINT", "MISCONCEPTION", "VISUAL_CUE", "WORKED_EXAMPLE"}
)


class RAGRetrieveRequest(BaseModel):
    query_id: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    content_type: RAGContentType
    hint_level: int | None = Field(default=None, ge=1, le=3)
    error_type: str | None = None
    difficulty: RAGDifficulty = "FOUNDATION"
    input_source: RAGInputSource = "TEXT"
    max_results: int = Field(default=3, ge=1, le=10)
    exclude_content_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_content_filters(self) -> "RAGRetrieveRequest":
        if self.content_type == "HINT" and self.hint_level is None:
            raise ValueError("hint_level is required when content_type is HINT")
        if self.content_type != "HINT" and self.hint_level is not None:
            raise ValueError("hint_level is only valid when content_type is HINT")
        if self.content_type in _ERROR_SPECIFIC_CONTENT and self.error_type is None:
            raise ValueError(
                f"error_type is required when content_type is {self.content_type}"
            )
        if self.content_type not in _ERROR_SPECIFIC_CONTENT and self.error_type is not None:
            raise ValueError(
                f"error_type is not valid when content_type is {self.content_type}"
            )
        return self


class RAGRetrievedContent(BaseModel):
    content_id: str
    content_type: RAGContentType
    hint_level: int | None
    text: str
    voice_text: str | None
    relevance_score: float
    concept_id: str
    error_type: str | None
    difficulty: RAGDifficulty
    version: str
    approval_status: str


class RAGQueryMetadata(BaseModel):
    retrieval_time_ms: int
    filters_applied: list[str]


class RAGRetrieveResponse(BaseModel):
    query_id: str
    results: list[RAGRetrievedContent]
    result_count: int
    fallback_used: bool
    query_metadata: RAGQueryMetadata
