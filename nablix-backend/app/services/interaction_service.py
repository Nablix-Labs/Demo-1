import re
from typing import cast, get_args

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.adapters.tutor_engine import apply_retrieved_content
from app.models.adapters import (
    AdapterContext,
    RAGResult,
    StudentModelResult,
    TutorResult,
    VisualCue,
)
from app.models.fields import Phase
from app.models.interaction import InteractionRequest, InteractionResponse
from app.models.session import SessionRecord
from app.services.session_service import (
    _get_owned_session,
    correct_answer_for,
    update_interaction_state,
)


_EMPTY_RAG = RAGResult(documents=[], retrieval_confidence=0.0)
_PHASE_VALUES: tuple[str, ...] = get_args(Phase)
_SPOKEN_DIGITS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}


async def run_tutor_pipeline(
    context: AdapterContext,
) -> tuple[RAGResult, StudentModelResult, TutorResult]:
    """Run the shared RAG, student-model, and tutor-engine adapter sequence."""

    adapters = get_adapters()
    # Classify first: error_type / response_strategy / chosen hint_level are tutor
    # outputs, so RAG can only target the right hint after evaluation.
    student = await adapters.student_model.assess(context)
    tutor = await adapters.tutor.evaluate(context, _EMPTY_RAG, student)

    rag = _EMPTY_RAG
    if tutor.response_strategy == "GUIDED_HINT":
        rag = await adapters.rag.retrieve(
            context, error_type=tutor.error_type, hint_level=tutor.hint_level
        )
        tutor = apply_retrieved_content(tutor, rag)
    return rag, student, tutor


def _student_message_from(request: InteractionRequest) -> str:
    if request.input_source == "TEXT":
        if request.text_input is None:
            raise HTTPException(status_code=422, detail="text_input is required for TEXT interactions.")
        return request.text_input

    if request.voice_transcript is None or len(request.voice_transcript.strip()) == 0:
        raise HTTPException(
            status_code=422,
            detail="voice_transcript is required for VOICE interactions.",
        )
    if request.transcript_confidence is None:
        raise HTTPException(
            status_code=422,
            detail="transcript_confidence is required for VOICE interactions.",
        )
    return _normalize_voice_transcript(request.voice_transcript)


def _normalize_voice_transcript(transcript: str) -> str:
    normalized = " ".join(transcript.split())
    for word, digit in _SPOKEN_DIGITS.items():
        normalized = re.sub(rf"\b{word}\b", digit, normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bis\s+equals?\s+to\b", "=", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bequals?\b", "=", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*=\s*", " = ", normalized)
    return " ".join(normalized.split())


def _current_hint_level_from(hint_count: int) -> int | None:
    if hint_count <= 0:
        return None
    return min(hint_count, 3)


def _next_phase_from(request: InteractionRequest, tutor: TutorResult | None) -> Phase:
    recommendation = tutor.next_phase_recommendation if tutor is not None else None
    if recommendation in _PHASE_VALUES:
        return cast(Phase, recommendation)
    return request.current_phase


def _next_hint_count_from(request: InteractionRequest) -> int:
    if request.interaction_type == "HINT_REQUEST":
        return request.hint_count + 1
    return request.hint_count


def _response_from(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
    message_voice: str,
    visual_cue: VisualCue | None,
    scaffold_steps: list[str],
    session_summary: str | None,
) -> InteractionResponse:
    return InteractionResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        current_phase=session.current_phase,
        current_question=session.current_question,
        interaction_mode=session.interaction_mode,
        voice_state=session.voice_state,
        canvas_state=session.canvas_state,
        ui_state=session.ui_state,
        message=message,
        message_voice=message_voice,
        show_canvas=session.show_canvas,
        show_hint_button=session.show_hint_button,
        show_visual_cue=session.show_visual_cue,
        visual_cue=visual_cue,
        show_scaffold_panel=session.show_scaffold_panel,
        scaffold_steps=scaffold_steps,
        allow_text_input=session.allow_text_input,
        allow_voice_input=session.allow_voice_input,
        hint_count=session.hint_count,
        phase_indicator=session.current_phase,
        session_summary=session_summary,
    )


async def process_interaction(request: InteractionRequest) -> InteractionResponse:
    """Run a student interaction through the tutor pipeline and return the session view.

    The raw RAG/student/tutor outputs still drive the response, but only the
    student-facing session fields are surfaced (per the module guide). The tutor
    still runs in full; its verdict fields just aren't echoed.
    """

    session: SessionRecord = _get_owned_session(request.session_id, request.student_id)
    student_message = _student_message_from(request)

    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        message=student_message,
        question=session.current_question,
        correct_answer=correct_answer_for(request.question_id),
        current_phase=request.current_phase,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        attempt_count=request.hint_count + 1,
        current_hint_level=_current_hint_level_from(request.hint_count),
        concept_id=request.concept_id,
    )
    adapters = get_adapters()
    safety_check = await adapters.safety.check(context)
    if not safety_check.passed:
        fallback = safety_check.safe_fallback_message or "Let's pause for a moment."
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            request.current_phase,
            request.hint_count,
            request.current_phase,
            request.transcript_confidence,
            request.canvas_snapshot_id,
            None,
            False,
            False,
            [],
        )
        return _response_from(
            request,
            updated_session,
            fallback,
            fallback,
            None,
            [],
            None,
        )

    _, _, tutor = await run_tutor_pipeline(context)
    tutor = tutor.model_copy(update={"safety_check": safety_check})
    for event in tutor.student_model_events:
        await adapters.student_model.update_from_event(event)

    visual_cue = tutor.visual_cue if tutor.visual_cue.show else None
    scaffold_steps = tutor.scaffold_steps_delivered
    next_phase = _next_phase_from(request, tutor)
    updated_session = update_interaction_state(
        request.session_id,
        request.student_id,
        next_phase,
        _next_hint_count_from(request),
        next_phase,
        request.transcript_confidence,
        request.canvas_snapshot_id,
        None,
        tutor.visual_cue.show,
        len(scaffold_steps) > 0,
        scaffold_steps,
    )

    return _response_from(
        request,
        updated_session,
        tutor.tutor_message,
        tutor.tutor_message_voice,
        visual_cue,
        scaffold_steps,
        None,
    )
