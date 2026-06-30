from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from enum import Enum

class ContentType(str, Enum):
    CONCEPT_EXPLANATION = "CONCEPT_EXPLANATION"
    PREREQUISITE = "PREREQUISITE"
    MISCONCEPTION = "MISCONCEPTION"
    HINT = "HINT"
    SCAFFOLD_STEP = "SCAFFOLD_STEP"
    REFLECTION_QUESTION = "REFLECTION_QUESTION"
    VISUAL_CUE = "VISUAL_CUE"
    WORKED_EXAMPLE = "WORKED_EXAMPLE"
    DIAGNOSTIC_QUESTION = "DIAGNOSTIC_QUESTION"
    MASTERY_CHECK = "MASTERY_CHECK"
    PRACTICE_QUESTION = "PRACTICE_QUESTION"

class ErrorType(str, Enum):
    ARITHMETIC_ERROR = "ARITHMETIC_ERROR"
    SIGN_ERROR = "SIGN_ERROR"
    OPPOSITE_OPERATION_ERROR = "OPPOSITE_OPERATION_ERROR"
    CONCEPTUAL_MISUNDERSTANDING = "CONCEPTUAL_MISUNDERSTANDING"
    PROCEDURAL_ERROR = "PROCEDURAL_ERROR"
    NOTATION_ISSUE = "NOTATION_ISSUE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class Difficulty(str, Enum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"

class DeliveryFormat(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"

class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class VisualCueType(str, Enum):
    EQUATION_BLOCK = "EQUATION_BLOCK"
    NUMBER_LINE = "NUMBER_LINE"
    GRAPH = "GRAPH"
    TABLE = "TABLE"
    HIGHLIGHTED_STEP = "HIGHLIGHTED_STEP"
    CONCEPT_CARD = "CONCEPT_CARD"

class OperationType(str, Enum):
    ADDITION = "ADDITION"
    SUBTRACTION = "SUBTRACTION"
    MULTIPLICATION = "MULTIPLICATION"
    DIVISION = "DIVISION"
    MIXED = "MIXED"

TYPES_REQUIRING_ERROR = {
    ContentType.HINT,
    ContentType.MISCONCEPTION,
    ContentType.VISUAL_CUE,
    ContentType.WORKED_EXAMPLE,
}

class ContentItem(BaseModel):
    content_id: str
    concept_id: str
    topic: str
    subtopic: str
    content_type: ContentType
    difficulty: Difficulty
    age_band: str
    language: str
    delivery_format: List[DeliveryFormat]
    text: str
    voice_text: Optional[str] = None
    error_type: Optional[ErrorType] = None
    hint_level: Optional[int] = None
    step_number: Optional[int] = None
    diagnostic_purpose: Optional[str] = None
    expected_answer: Optional[str] = None
    expected_method: Optional[str] = None
    visual_cue_type: Optional[VisualCueType] = None
    operation_type: Optional[OperationType] = None
    version: str
    approval_status: ApprovalStatus
    created_by: str
    approved_by: Optional[str] = None
    approved_date: Optional[str] = None

    @field_validator("content_id")
    @classmethod
    def content_id_format(cls, v):
        if not v or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError(f"content_id must be alphanumeric with underscores, got: {v}")
        return v

    @field_validator("age_band")
    @classmethod
    def age_band_mvp(cls, v):
        if v != "11-14":
            raise ValueError(f"age_band must be '11-14' for MVP, got: {v}")
        return v

    @field_validator("language")
    @classmethod
    def language_mvp(cls, v):
        if v != "en":
            raise ValueError(f"language must be 'en' for MVP, got: {v}")
        return v

    @field_validator("hint_level")
    @classmethod
    def hint_level_range(cls, v):
        if v is not None and v not in (1, 2, 3):
            raise ValueError(f"hint_level must be 1, 2, or 3, got: {v}")
        return v

    @model_validator(mode="after")
    def check_conditional_fields(self):
        ct = self.content_type

        if DeliveryFormat.VOICE in self.delivery_format and not self.voice_text:
            raise ValueError("voice_text is required when VOICE is in delivery_format")

        if ct in TYPES_REQUIRING_ERROR and self.error_type is None:
            raise ValueError(f"error_type is required for content_type {ct.value}")
        if ct not in TYPES_REQUIRING_ERROR and self.error_type is not None:
            raise ValueError(f"error_type must be null for content_type {ct.value}")

        if ct == ContentType.HINT and self.hint_level is None:
            raise ValueError("hint_level is required for HINT")
        if ct != ContentType.HINT and self.hint_level is not None:
            raise ValueError(f"hint_level must be null for content_type {ct.value}")

        if ct == ContentType.SCAFFOLD_STEP and self.step_number is None:
            raise ValueError("step_number is required for SCAFFOLD_STEP")
        if ct != ContentType.SCAFFOLD_STEP and self.step_number is not None:
            raise ValueError(f"step_number must be null for content_type {ct.value}")

        if ct == ContentType.DIAGNOSTIC_QUESTION:
            if not self.diagnostic_purpose:
                raise ValueError("diagnostic_purpose is required for DIAGNOSTIC_QUESTION")
            if not self.expected_answer:
                raise ValueError("expected_answer is required for DIAGNOSTIC_QUESTION")
            if not self.expected_method:
                raise ValueError("expected_method is required for DIAGNOSTIC_QUESTION")
        else:
            if self.diagnostic_purpose:
                raise ValueError(f"diagnostic_purpose must be null for {ct.value}")
            if self.expected_method:
                raise ValueError(f"expected_method must be null for {ct.value}")

        if ct == ContentType.MASTERY_CHECK and not self.expected_answer:
            raise ValueError("expected_answer is required for MASTERY_CHECK")

        if ct == ContentType.VISUAL_CUE and self.visual_cue_type is None:
            raise ValueError("visual_cue_type is required for VISUAL_CUE")
        if ct != ContentType.VISUAL_CUE and self.visual_cue_type is not None:
            raise ValueError(f"visual_cue_type must be null for {ct.value}")

        if self.approval_status == ApprovalStatus.APPROVED:
            if not self.approved_by:
                raise ValueError("approved_by is required when approval_status is APPROVED")
            if not self.approved_date:
                raise ValueError("approved_date is required when approval_status is APPROVED")

        return self

def validate_item(data: dict) -> tuple[bool, ContentItem | None, str | None]:
    try:
        item = ContentItem(**data)
        return True, item, None
    except Exception as e:
        return False, None, str(e)

def validate_batch(items: list[dict]) -> tuple[list[ContentItem], list[dict]]:
    valid = []
    errors = []
    seen_ids = set()

    for i, data in enumerate(items):
        cid = data.get("content_id", f"item_index_{i}")

        if cid in seen_ids:
            errors.append({"content_id": cid, "error": f"Duplicate content_id: {cid}"})
            continue
        seen_ids.add(cid)

        is_valid, item, error = validate_item(data)
        if is_valid:
            valid.append(item)
        else:
            errors.append({"content_id": cid, "error": error})

    return valid, errors
