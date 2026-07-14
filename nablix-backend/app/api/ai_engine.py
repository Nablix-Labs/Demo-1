from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.ai_engine.schemas import CanvasTextRegion, HintLevel, InputSource, LearningPhase, TutorResponse
from app.models.adapters import ConversationMessage


router = APIRouter()


class AiEngineClassifyRequest(BaseModel):
    student_input: str
    current_phase: LearningPhase
    question: str
    correct_answer: str
    input_source: InputSource
    transcript_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    attempt_count: int = Field(default=1, ge=0)
    current_hint_level: HintLevel | None = None
    ocr_text: str | None = None
    canvas_text: str | None = None
    concept_id: str | None = None
    difficulty: str = "FOUNDATION"
    max_hint_results: int = Field(default=3, ge=1)
    exclude_content_ids: list[str] = Field(default_factory=list)
    canvas_regions: list[CanvasTextRegion] = Field(default_factory=list)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def map_integration_field_names(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        normalized_data: dict[str, object] = dict(data)
        if "current_phase" not in normalized_data and "phase" in normalized_data:
            normalized_data["current_phase"] = normalized_data["phase"]
        if "question" not in normalized_data and "question_context" in normalized_data:
            normalized_data["question"] = normalized_data["question_context"]
        if "correct_answer" not in normalized_data and "expected_answer" in normalized_data:
            normalized_data["correct_answer"] = normalized_data["expected_answer"]
        return normalized_data


def _combined_student_input(request: AiEngineClassifyRequest) -> str:
    text_parts: list[str] = [request.student_input]
    if request.ocr_text is not None and len(request.ocr_text.strip()) > 0:
        text_parts.append(f"OCR text: {request.ocr_text}")
    if request.canvas_text is not None and len(request.canvas_text.strip()) > 0:
        text_parts.append(f"Canvas text: {request.canvas_text}")
    return "\n".join(text_parts)


def _classification_request_from(request: AiEngineClassifyRequest) -> ClassificationRequest:
    return ClassificationRequest(
        question=request.question,
        correct_answer=request.correct_answer,
        student_input=_combined_student_input(request),
        current_phase=request.current_phase,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        attempt_count=request.attempt_count,
        current_hint_level=request.current_hint_level,
        concept_id=request.concept_id,
        difficulty=request.difficulty,
        max_hint_results=request.max_hint_results,
        exclude_content_ids=request.exclude_content_ids,
        canvas_regions=request.canvas_regions,
        conversation_history=request.conversation_history,
    )


@router.post("/classify", response_model=TutorResponse)
async def classify_tutor_input(request: AiEngineClassifyRequest) -> TutorResponse:
    return classify_student_response(_classification_request_from(request))
