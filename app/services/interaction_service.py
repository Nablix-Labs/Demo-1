import re
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.provider import get_adapters
from app.adapters.tutor_engine import apply_retrieved_content
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.exceptions import QuestionFetchError
from app.core.logger import logger
from app.models.adapters import (
    AdapterContext,
    ConversationAction,
    ConversationMessage,
    ConversationState,
    ExpectedStudentResponse,
    RAGResult,
    StudentModelResult,
    TutorAction,
    TutorResult,
    VisualCue,
)
from app.models.fields import Phase
from app.models.interaction import (
    InteractionRequest,
    InteractionResponse,
    StaleTurnResponse,
)
from app.models.session import (
    PhaseTransitionRecord,
    QuestionAttemptRecord,
    SessionRecord,
    SessionSummary,
)
from app.services.phase_transition import (
    DEFAULT_TRANSITION_MESSAGE,
    PHASE_COUNTER_RESETS,
    TRANSITION_MESSAGES,
    resolve_transition,
)
from app.services.session_service import (
    _get_owned_session_for_turn,
    cache_interaction_response,
    get_canvas_submission,
    get_next_question,
    interaction_lock_for,
    last_interaction_response_for,
    update_interaction_state,
)


_EMPTY_RAG = RAGResult(documents=[], retrieval_confidence=0.0)
_LOW_CONFIDENCE_MESSAGE = "I’m not sure I heard that clearly. Could you say it again?"
_STALE_TURN_MESSAGE = (
    "The conversation has moved forward. Please use the latest tutor response."
)
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
        if context.correct_answer is None:
            raise ValueError("correct_answer is required before applying retrieved tutor content")
        tutor = apply_retrieved_content(tutor, rag, context.correct_answer)
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
    normalized = re.sub(
        r"\b(?:is\s+)?equals?\s+to\b",
        "=",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\bequals?\b", "=", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*=\s*", " = ", normalized)
    return " ".join(normalized.split())


def _is_acknowledgement(message: str, rules: ClassifierRulesConfig) -> bool:
    normalized_message: str = re.sub(r"[^a-z0-9\s]", "", message.lower()).strip()
    return normalized_message in rules.conversation_rules.acknowledgement_phrases


def _updated_conversation_history(
    history: list[ConversationMessage],
    student_message: str,
    tutor_message: str,
    max_messages: int,
) -> list[ConversationMessage]:
    updated_history: list[ConversationMessage] = [
        *history,
        ConversationMessage(role="user", content=student_message),
        ConversationMessage(role="assistant", content=tutor_message),
    ]
    if max_messages == 0:
        return []
    return updated_history[-max_messages:]


def _recent_conversation_history(
    history: list[ConversationMessage],
    max_messages: int,
) -> list[ConversationMessage]:
    if max_messages == 0:
        return []
    return history[-max_messages:]


def _conversation_state_from_session(session: SessionRecord) -> ConversationState:
    return ConversationState(
        last_tutor_action=session.last_tutor_action,
        expected_student_response=session.expected_student_response,
    )


def _current_hint_level_from(hint_count: int) -> int | None:
    if hint_count <= 0:
        return None
    return min(hint_count, 3)


def _independent_correct_in_session(session: SessionRecord) -> int:
    # Unaided corrects in any phase — the same semantics as the classifier's
    # independent_success flag, which Saravanan's promotion gate counts.
    return sum(
        attempt.evaluation == "CORRECT" and attempt.hint_level_used == 0
        for attempt in session.per_question_history
    )


def _next_hint_count_from(session: SessionRecord, request: InteractionRequest) -> int:
    if request.interaction_type == "HINT_REQUEST":
        return session.hint_count + 1
    return session.hint_count


def _new_tutor_turn_id() -> str:
    return f"TUTOR-{uuid4()}"


def _voice_turn_updates(
    request: InteractionRequest,
    last_tutor_action: TutorAction,
    expected_student_response: ExpectedStudentResponse,
) -> dict[str, object]:
    updates: dict[str, object] = {
        "last_tutor_action": last_tutor_action,
        "expected_student_response": expected_student_response,
    }
    if request.input_source != "VOICE":
        return updates
    if request.turn_id is None:
        raise RuntimeError("validated VOICE interaction is missing turn_id")
    updates.update(
        {
            "last_processed_turn_id": request.turn_id,
            "last_tutor_turn_id": _new_tutor_turn_id(),
        }
    )
    return updates


def _conversation_state_for(
    conversation_action: ConversationAction,
    question_completed: bool,
    evaluation: str | None,
) -> tuple[TutorAction, ExpectedStudentResponse]:
    if conversation_action == "ADVANCE_TO_NEXT_QUESTION":
        return "ADVANCED_QUESTION", "ANSWER"
    if conversation_action == "GIVE_HINT":
        return "GAVE_HINT", "ANSWER"
    if conversation_action == "REQUEST_CLARIFICATION":
        return "REQUESTED_CLARIFICATION", "CLARIFICATION"
    if conversation_action == "REQUEST_EXPLANATION":
        return "REQUESTED_EXPLANATION", "EXPLANATION"
    if question_completed:
        return "CONFIRMED_CORRECT_ANSWER", "ACKNOWLEDGEMENT_OR_CONTINUE"
    if evaluation in {"PARTIALLY_CORRECT", "INCORRECT"}:
        return "GAVE_INCORRECT_FEEDBACK", "ANSWER"
    return "ASKED_QUESTION", "ANSWER"


def _stale_turn_response(session: SessionRecord) -> StaleTurnResponse:
    return StaleTurnResponse(
        status="STALE_TURN",
        accepted_turn_id=None,
        expected_previous_tutor_turn_id=session.last_tutor_turn_id,
        conversation_action="WAIT_FOR_STUDENT",
        attempt_increment=0,
        retry_safe=False,
        message=_STALE_TURN_MESSAGE,
    )


def _duplicate_turn_response(
    request: InteractionRequest,
    session: SessionRecord,
) -> InteractionResponse | None:
    if (
        request.input_source != "VOICE"
        or request.turn_id != session.last_processed_turn_id
    ):
        return None
    response = last_interaction_response_for(session.session_id)
    if response is None:
        raise RuntimeError(
            f"cached response is missing for duplicate session_id={session.session_id} "
            f"turn_id={request.turn_id}"
        )
    return response.model_copy(
        update={
            "status": "DUPLICATE_TURN",
            "conversation_action": "WAIT_FOR_STUDENT",
            "attempt_increment": 0,
            "retry_safe": True,
        }
    )


def _turn_is_stale(request: InteractionRequest, session: SessionRecord) -> bool:
    if request.input_source != "VOICE":
        return False
    return (
        request.previous_tutor_turn_id != session.last_tutor_turn_id
        or request.question_id != session.question_id
    )


async def next_question_updates(
    session: SessionRecord, phase: Phase
) -> dict[str, object] | None:
    """Session updates that route to the next unseen question, or None when
    the bank has nothing new for the phase."""

    fetched = await get_next_question(
        session.concept_id, phase, session.served_question_ids
    )
    if fetched is None or fetched[2] == session.question_id:
        return None
    question_text, correct_answer, question_id = fetched
    return {
        "current_question": question_text,
        "question_id": question_id,
        "correct_answer": correct_answer,
        "served_question_ids": [*session.served_question_ids, question_id],
        "question_number": session.question_number + 1,
        "attempt_count": 0,
        "hint_count": 0,
        "question_completed": False,
    }


def _response_from(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
    message_voice: str,
    visual_cue: VisualCue | None,
    scaffold_steps: list[str],
    session_summary: SessionSummary | None,
    conversation_action: ConversationAction,
    attempt_increment: int,
    status: Literal["CLARIFICATION_REQUIRED"] | None,
    retry_safe: bool | None,
    previous_phase: Phase | None = None,
) -> InteractionResponse:
    # previous_phase is only passed on the turn a 6.7 transition executed;
    # message and voice are the same hardcoded string per spec.
    transition_message = (
        TRANSITION_MESSAGES.get(
            (previous_phase, session.current_phase), DEFAULT_TRANSITION_MESSAGE
        )
        if previous_phase is not None
        else None
    )
    return InteractionResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        status=status,
        accepted_turn_id=(
            session.last_processed_turn_id
            if request.input_source == "VOICE"
            else None
        ),
        tutor_turn_id=(
            session.last_tutor_turn_id if request.input_source == "VOICE" else None
        ),
        conversation_action=conversation_action,
        expects_student_response=session.expected_student_response != "NONE",
        expected_student_response=session.expected_student_response,
        retry_safe=retry_safe,
        expected_previous_tutor_turn_id=None,
        attempt_increment=attempt_increment,
        phase_changed=previous_phase is not None,
        previous_phase=previous_phase,
        phase_transition_message=transition_message,
        phase_transition_voice=transition_message,
        current_phase=session.current_phase,
        question_id=session.question_id,
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
        attempt_count=session.attempt_count,
        question_completed=session.question_completed,
        answer_value_confirmed=session.answer_value_confirmed,
        phase_indicator=session.current_phase,
        recommended_entry_phase=session.recommended_entry_phase,
        session_summary=session_summary,
    )


def _cache_voice_response(
    request: InteractionRequest,
    response: InteractionResponse,
) -> InteractionResponse:
    if request.input_source == "VOICE":
        cache_interaction_response(request.session_id, response)
    return response


async def process_interaction(
    request: InteractionRequest,
    access_token: str,
) -> InteractionResponse | StaleTurnResponse:
    async with interaction_lock_for(request.session_id):
        return await _process_interaction(request, access_token)


async def _process_interaction(
    request: InteractionRequest,
    access_token: str,
) -> InteractionResponse | StaleTurnResponse:
    """Run a student interaction through the tutor pipeline and return the session view.

    The raw RAG/student/tutor outputs still drive the response, but only the
    student-facing session fields are surfaced (per the module guide). The tutor
    still runs in full; its verdict fields just aren't echoed.
    """

    session: SessionRecord = _get_owned_session_for_turn(
        request.session_id,
        request.student_id,
        request.current_phase,
        request.hint_count,
    )
    duplicate_response = _duplicate_turn_response(request, session)
    if duplicate_response is not None:
        return duplicate_response
    if _turn_is_stale(request, session):
        return _stale_turn_response(session)

    student_message = _student_message_from(request)
    rules: ClassifierRulesConfig = load_classifier_rules()

    if (
        request.input_source == "VOICE"
        and request.transcript_confidence is not None
        and request.transcript_confidence < rules.low_transcript_confidence_threshold
    ):
        clarification_history = _updated_conversation_history(
            session.conversation_history,
            student_message,
            _LOW_CONFIDENCE_MESSAGE,
            rules.conversation_rules.max_recent_messages,
        )
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session.current_phase,
            session.hint_count,
            session.current_phase,
            request.transcript_confidence,
            request.canvas_snapshot_id,
            None,
            False,
            False,
            [],
            {
                "attempt_count": session.attempt_count,
                "question_completed": session.question_completed,
                "conversation_history": clarification_history,
                **_voice_turn_updates(
                    request,
                    "REQUESTED_CLARIFICATION",
                    "CLARIFICATION",
                ),
            },
        )
        return _cache_voice_response(
            request,
            _response_from(
                request,
                updated_session,
                _LOW_CONFIDENCE_MESSAGE,
                _LOW_CONFIDENCE_MESSAGE,
                None,
                [],
                None,
                "REQUEST_CLARIFICATION",
                0,
                "CLARIFICATION_REQUIRED",
                None,
            ),
        )

    if (
        session.question_completed
        and session.last_tutor_action == "CONFIRMED_CORRECT_ANSWER"
        and session.expected_student_response == "ACKNOWLEDGEMENT_OR_CONTINUE"
        and _is_acknowledgement(student_message, rules)
    ):
        completion_message: str = rules.messages.CONTEXTUAL_ACKNOWLEDGEMENT
        completed_history: list[ConversationMessage] = _updated_conversation_history(
            session.conversation_history,
            student_message,
            completion_message,
            rules.conversation_rules.max_recent_messages,
        )
        advance = await next_question_updates(session, session.current_phase)
        if advance is None:
            raise QuestionFetchError(session.concept_id, session.current_phase)
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session.current_phase,
            session.hint_count,
            session.current_phase,
            request.transcript_confidence,
            request.canvas_snapshot_id,
            None,
            False,
            False,
            [],
            {
                "attempt_count": session.attempt_count,
                "conversation_history": completed_history,
                **advance,
                **_voice_turn_updates(request, "ADVANCED_QUESTION", "ANSWER"),
            },
        )
        return _cache_voice_response(
            request,
            _response_from(
                request,
                updated_session,
                completion_message,
                completion_message,
                None,
                [],
                None,
                "ADVANCE_TO_NEXT_QUESTION",
                0,
                None,
                None,
            ),
        )

    recent_history: list[ConversationMessage] = _recent_conversation_history(
        session.conversation_history,
        rules.conversation_rules.max_recent_messages,
    )
    canvas_submission = get_canvas_submission(session, request.canvas_snapshot_id)
    ocr = canvas_submission.ocr if canvas_submission is not None else None

    next_attempt_count = (
        session.attempt_count + 1
        if (
            request.interaction_type == "ANSWER_SUBMISSION"
            and not session.answer_value_confirmed
        )
        else session.attempt_count
    )
    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        source_turn_id=request.turn_id or f"TURN-{uuid4().hex.upper()}",
        message=student_message,
        question=session.current_question,
        # Grade against the session's question: after a 6.7 transition swaps
        # the question, the request's id from the frontend may be stale.
        correct_answer=session.correct_answer,
        current_phase=session.current_phase,
        input_source=request.input_source,
        transcript_confidence=request.transcript_confidence,
        attempt_count=next_attempt_count,
        independent_correct_in_session=_independent_correct_in_session(session),
        question_completed=session.question_completed,
        answer_value_confirmed=session.answer_value_confirmed,
        question_number=session.question_number,
        current_hint_level=_current_hint_level_from(session.hint_count),
        concept_id=session.concept_id,
        conversation_history=recent_history,
        conversation_state=_conversation_state_from_session(session),
        detected_equation=ocr.detected_equation if ocr is not None else None,
        detected_steps=ocr.detected_steps if ocr is not None else [],
        ocr_confidence=ocr.confidence if ocr is not None else None,
        canvas_regions=ocr.detected_regions if ocr is not None else [],
    )
    adapters = get_adapters()
    safety_check = await adapters.safety.check(context)
    if not safety_check.passed:
        fallback = safety_check.safe_fallback_message or "Let's pause for a moment."
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session.current_phase,
            session.hint_count,
            session.current_phase,
            request.transcript_confidence,
            request.canvas_snapshot_id,
            None,
            False,
            False,
            [],
            {
                "attempt_count": session.attempt_count,
                "question_completed": session.question_completed,
                "conversation_history": _updated_conversation_history(
                    session.conversation_history,
                    student_message,
                    fallback,
                    rules.conversation_rules.max_recent_messages,
                ),
                **_voice_turn_updates(
                    request,
                    session.last_tutor_action,
                    session.expected_student_response,
                ),
            },
        )
        return _cache_voice_response(
            request,
            _response_from(
                request,
                updated_session,
                fallback,
                fallback,
                None,
                [],
                None,
                "WAIT_FOR_STUDENT",
                0,
                None,
                None,
            ),
        )

    _, student, tutor = await run_tutor_pipeline(context)
    tutor = tutor.model_copy(update={"safety_check": safety_check})
    for event in tutor.student_model_events:
        student = await adapters.student_model.update_from_event(
            event,
            context,
            access_token,
        )

    visual_cue = tutor.visual_cue if tutor.visual_cue.show else None
    scaffold_steps = tutor.scaffold_steps_delivered
    conversation_history: list[ConversationMessage] = _updated_conversation_history(
        session.conversation_history,
        student_message,
        tutor.tutor_message,
        rules.conversation_rules.max_recent_messages,
    )

    effective_attempt_increment: int = (
        tutor.attempt_increment
        if request.interaction_type == "ANSWER_SUBMISSION"
        else 0
    )
    completed: bool = (
        tutor.question_completed
        if request.interaction_type == "ANSWER_SUBMISSION"
        else session.question_completed
    )
    applied_attempt_count: int = session.attempt_count + effective_attempt_increment
    # Chirudeva 6.7: Saravanan's recommendation is the only phase authority;
    # resolve_transition guards against invalid or unrecognised moves.
    recommended: str | None = student.recommended_entry_phase
    new_phase = resolve_transition(session.current_phase, recommended)
    logger.info(
        "phase_transition_evaluated",
        extra={
            "session_id": session.session_id,
            "current_phase": session.current_phase,
            "student_model_recommended_phase": recommended,
            "phase_changed": new_phase is not None,
            "attempt_count": applied_attempt_count,
        },
    )

    next_hint_count: int = _next_hint_count_from(session, request)
    conversation_action: ConversationAction = tutor.recommended_conversation_action
    # Persisted every turn: the real attempt counter and completion state Sanya
    # reads back on the next turn.
    state_updates: dict[str, object] = {
        "attempt_count": applied_attempt_count,
        "question_completed": completed,
        "answer_value_confirmed": tutor.answer_value_confirmed,
        "conversation_history": conversation_history,
        "recommended_entry_phase": recommended,
        "last_student_model": student,
    }
    if (
        request.interaction_type == "ANSWER_SUBMISSION"
        and effective_attempt_increment == 1
    ):
        state_updates["per_question_history"] = [
            *session.per_question_history,
            QuestionAttemptRecord(
                question_id=session.question_id,
                question_text=session.current_question,
                phase=session.current_phase,
                evaluation=tutor.evaluation,
                error_type=tutor.error_type if tutor.evaluation != "CORRECT" else None,
                input_source=request.input_source,
                hint_level_used=tutor.hint_level,
                attempted_at=datetime.now(timezone.utc),
            ),
        ]
    elif request.interaction_type == "HINT_REQUEST":
        state_updates["hint_levels_used"] = [*session.hint_levels_used, next_hint_count]
    if new_phase is not None:
        # Fetch before committing any state: an Aditya failure raises here,
        # so the session (and its phase) is never touched — rollback for free.
        fetched = await get_next_question(
            session.concept_id, new_phase, session.served_question_ids
        )
        if fetched is None:
            raise QuestionFetchError(session.concept_id, new_phase)
        question_text, correct_answer, question_id = fetched
        state_updates.update(
            {
                "previous_phase": session.current_phase,
                "current_question": question_text,
                "question_id": question_id,
                "correct_answer": correct_answer,
                "served_question_ids": [*session.served_question_ids, question_id],
                "question_number": session.question_number + 1,
                "attempt_count": 0,
                "hint_count": 0,
                "question_completed": False,
                "answer_value_confirmed": False,
                "conversation_history": [],
                "phase_transitions": [
                    *session.phase_transitions,
                    PhaseTransitionRecord(
                        previous_phase=session.current_phase,
                        current_phase=new_phase,
                        entry_reason="STUDENT_MODEL_RECOMMENDATION",
                        transitioned_at=datetime.now(timezone.utc),
                    ),
                ],
                **PHASE_COUNTER_RESETS.get(new_phase, {}),
            }
        )
        conversation_action = "ADVANCE_TO_NEXT_QUESTION"
    elif conversation_action == "ADVANCE_TO_NEXT_QUESTION":
        advance = await next_question_updates(session, session.current_phase)
        if advance is None:
            raise QuestionFetchError(session.concept_id, session.current_phase)
        advance["answer_value_confirmed"] = False
        advance["conversation_history"] = []
        state_updates.update(advance)

    resulting_question_completed: bool = bool(
        state_updates.get("question_completed", completed)
    )
    last_tutor_action, expected_student_response = _conversation_state_for(
        conversation_action,
        resulting_question_completed,
        tutor.evaluation,
    )
    state_updates.update(
        _voice_turn_updates(
            request,
            last_tutor_action,
            expected_student_response,
        )
    )

    next_phase = new_phase if new_phase is not None else session.current_phase
    updated_session = update_interaction_state(
        request.session_id,
        request.student_id,
        next_phase,
        next_hint_count,
        next_phase,
        request.transcript_confidence,
        request.canvas_snapshot_id,
        None,
        tutor.visual_cue.show,
        len(scaffold_steps) > 0,
        scaffold_steps,
        state_updates,
    )

    return _cache_voice_response(
        request,
        _response_from(
            request,
            updated_session,
            tutor.tutor_message,
            tutor.tutor_message_voice,
            visual_cue,
            scaffold_steps,
            None,
            conversation_action,
            effective_attempt_increment,
            None,
            None,
            previous_phase=session.current_phase if new_phase is not None else None,
        ),
    )
