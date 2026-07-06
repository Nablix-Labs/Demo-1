"""Tutor-engine adapter.

The tutor engine is the final decision point in the text pipeline. It receives
student context, retrieved curriculum material, and student-model state, then
returns the frontend-facing tutoring decision fields.
"""

from typing import NoReturn

from pydantic import ValidationError

from app.ai_engine.classifier import ClassificationRequest, classify_student_response
from app.ai_engine.schemas import TutorResponse
from app.adapters.http_utils import JsonObject, post_json
from app.core.config import Settings
from app.core.exceptions import AdapterError
from app.models.adapters import (
    AdapterContext,
    AnnotationIntent,
    CanvasFeedback,
    RAGResult,
    SafetyCheckResult,
    StudentModelResult,
    StudentModelEvent,
    TutorEngineRequest,
    TutorMistakeClassification,
    TutorResult,
    VisualCue,
)


class TutorEngineServiceAdapter:
    """Produces tutor feedback through mock data or a live tutor service.

    The service-facing `evaluate` method stays stable while `call`,
    `parse_response`, and `handle_error` implement the replaceable adapter
    pattern from submodule 6.3.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def evaluate(
        self,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        """Service-facing method used by interaction and hint workflows."""

        request = TutorEngineRequest(context=context, rag=rag, student=student)
        return await self.call(request)

    async def call(self, request: TutorEngineRequest) -> TutorResult:
        """Return mock tutor feedback or call the live tutor engine."""

        if self._settings.use_mock_tutor:
            return self._mock_response(request)

        payload: JsonObject = request.model_dump(mode="json")
        try:
            response = await post_json(
                "tutor_engine",
                self._settings.tutor_engine_url,
                payload,
                self._settings.adapter_request_timeout_seconds,
                self._settings.adapter_request_retry_count,
            )
            return self.parse_response(response)
        except AdapterError as error:
            self.handle_error(error)

    def parse_response(self, response: dict[str, object]) -> TutorResult:
        try:
            return TutorResult.model_validate(response)
        except ValidationError as error:
            raise AdapterError(
                "tutor_engine",
                f"invalid response body={response}: {error}",
            ) from error

    def handle_error(self, error: AdapterError) -> NoReturn:
        raise error

    def _mock_response(self, request: TutorEngineRequest) -> TutorResult:
        """Return AI Engine feedback when context has a question, else mock data."""

        context = request.context
        if context.question is not None and context.correct_answer is not None:
            ai_response = classify_student_response(
                ClassificationRequest(
                    question=context.question,
                    correct_answer=context.correct_answer,
                    student_input=context.message,
                    current_phase=context.current_phase or "GUIDED_PRACTICE",
                    input_source=context.input_source or "TEXT",
                    transcript_confidence=context.transcript_confidence,
                    attempt_count=context.attempt_count or 1,
                    current_hint_level=context.current_hint_level,
                    concept_id=context.concept_id,
                    difficulty="FOUNDATION",
                    max_hint_results=3,
                    exclude_content_ids=[],
                    canvas_regions=[region.model_dump() for region in context.canvas_regions],
                )
            )
            return _tutor_result_from_ai_response(ai_response)

        return TutorResult(
            evaluation="INCORRECT",
            error_type="ARITHMETIC_ERROR",
            intent="SUBMITTING_ANSWER",
            response_strategy="GUIDED_HINT",
            tutor_message="Check your arithmetic carefully.",
            tutor_message_voice="Check your arithmetic carefully.",
            voice_optimised=True,
            hint_level=1,
            scaffold_steps_delivered=[],
            next_phase_recommendation="GUIDED_PRACTICE",
            answer_reveal_allowed=False,
            confidence=0.91,
            input_source="TEXT",
            transcript_confidence=None,
            safety_check=SafetyCheckResult(passed=True),
            student_model_events=[
                StudentModelEvent(
                    event_type="INCORRECT_ATTEMPT",
                    evaluation="INCORRECT",
                    error_type="ARITHMETIC_ERROR",
                    hint_level_used=0,
                    independent_success=False,
                )
            ],
        )


class MockTutorEngineAdapter(TutorEngineServiceAdapter):
    """Compatibility wrapper for tests or imports that need a mock-only adapter."""

    def __init__(self) -> None:
        super().__init__(Settings(use_mock_tutor=True))


def _tutor_result_from_ai_response(response: TutorResponse) -> TutorResult:
    return TutorResult(
        evaluation=response.evaluation or "NO_ATTEMPT",
        error_type=response.error_type or "UNKNOWN_ERROR",
        intent=response.intent,
        response_strategy=response.response_strategy,
        tutor_message=response.tutor_message,
        tutor_message_voice=response.tutor_message_voice_optimised,
        voice_optimised=response.voice_optimised,
        hint_level=response.hint_level or 0,
        scaffold_steps_delivered=response.scaffold_steps_delivered,
        visual_cue=VisualCue(
            show=response.visual_cue.show,
            cue_type=response.visual_cue.cue_type,
            description=response.visual_cue.description,
        ),
        canvas_feedback=CanvasFeedback(),
        mistake_classification=(
            TutorMistakeClassification(
                status=response.mistake_classification.status,
                mistake_step_id=response.mistake_classification.mistake_step_id,
                target_text=response.mistake_classification.target_text,
                target_span=(
                    (
                        response.mistake_classification.target_span[0],
                        response.mistake_classification.target_span[1],
                    )
                    if response.mistake_classification.target_span is not None
                    else None
                ),
                replacement_text=response.mistake_classification.replacement_text,
                confidence=response.mistake_classification.confidence,
            )
            if response.mistake_classification is not None
            else None
        ),
        annotation_intents=[
            AnnotationIntent(
                kind=intent.kind,
                target_step_id=intent.target_step_id,
                text=intent.text,
                placement=intent.placement,
            )
            for intent in response.annotation_intents
        ],
        next_phase_recommendation=response.next_phase_recommendation,
        answer_reveal_allowed=response.answer_reveal_allowed,
        confidence=response.confidence,
        input_source=response.input_source,
        transcript_confidence=response.transcript_confidence,
        safety_check=SafetyCheckResult(
            passed=response.safety_check.passed,
            flag_type=response.safety_check.flag_type,
            action_taken=response.safety_check.action_taken,
        ),
        student_model_events=[
            StudentModelEvent(
                event_type=event.event_type,
                evaluation=event.evaluation or "NO_ATTEMPT",
                error_type=event.error_type,
                hint_level_used=event.hint_level_used,
                independent_success=event.independent_success,
            )
            for event in response.student_model_events
        ],
    )


# Strategies whose message body should be the retrieved curriculum text: the
# classifier decides the strategy, RAG supplies the words.
_CONTENT_STRATEGIES = {"GUIDED_HINT", "SCAFFOLD", "PROVIDE_WORKED_EXAMPLE"}


def apply_retrieved_content(result: TutorResult, rag: RAGResult) -> TutorResult:
    """Use the top retrieved document as the tutor message for content-bearing
    strategies. No documents or a non-content strategy → leave the classifier's
    message untouched. Called by run_tutor_pipeline after classification, so the
    retrieval already used the classifier's chosen hint level.
    """
    if not rag.documents or result.response_strategy not in _CONTENT_STRATEGIES:
        return result
    top_document = rag.documents[0]
    if top_document.source == "mock_curriculum":
        return result

    content = top_document.content
    return result.model_copy(update={"tutor_message": content, "tutor_message_voice": content})
