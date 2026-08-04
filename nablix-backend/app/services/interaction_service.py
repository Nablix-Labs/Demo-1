import re
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException

from app.adapters.base import StudentModelAdapter
from app.adapters.provider import get_adapters
from app.ai_engine.classifier import (
    contains_answer_reveal,
    detect_student_intent,
    normalize_exact_notation,
)
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.logger import logger
from app.models.adapters import (
    AdapterContext,
    ConversationAction,
    ConversationMessage,
    ConversationState,
    ExpectedStudentResponse,
    Phase2PromptContext,
    RAGResult,
    StudentModelResult,
    TutorAction,
    TutorResult,
    VisualCue,
)
from app.models.fields import Phase
from app.models.guided_learning import ScaffoldEvaluationContext
from app.models.interaction import (
    InteractionRequest,
    InteractionResponse,
    StaleTurnResponse,
)
from app.models.session import (
    QuestionAttemptRecord,
    SessionRecord,
    SessionSummary,
)
from app.models.student_model_session import (
    AnswerSpec,
    GuidedAttemptEvent,
    GuidedPhaseCompletedEvent,
    GuidedQuestionSetRequestedEvent,
    GuidedSupportEvent,
    IndependentQuestionSetRequestedEvent,
    IndependentRetryCompletedEvent,
    Phase2RepairResult,
    StudentModelSessionEventResponse,
    StudentModelQuestion,
    SupportUsed,
)
from app.services.phase_transition import (
    DEFAULT_TRANSITION_MESSAGE,
    TRANSITION_MESSAGES,
)
from app.services.session_service import (
    _apply_schema_event,
    _get_owned_session_for_turn,
    cache_interaction_response,
    get_canvas_submission,
    interaction_lock_for,
    last_interaction_response_for,
    update_interaction_state,
)
from app.services.student_model_session import (
    PHASE_FROM_STUDENT_MODEL,
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
_SUPPORT_RANK: tuple[SupportUsed, ...] = (
    "NONE",
    "HINT",
    "VISUAL_CUE",
    "SCAFFOLD",
    "PARALLEL_EXAMPLE",
    "TUTOR_SOLVED",
)


async def run_tutor_pipeline(
    context: AdapterContext,
) -> tuple[RAGResult, StudentModelResult, TutorResult]:
    """Run the shared RAG, student-model, and tutor-engine adapter sequence."""

    adapters = get_adapters()
    # Classify first: error_type / response_strategy / chosen hint_level are tutor
    # outputs, so RAG can only target the right hint after evaluation.
    student = await adapters.student_model.assess(context)
    tutor = await adapters.tutor.evaluate(context, _EMPTY_RAG, student)

    return _EMPTY_RAG, student, tutor


async def process_answer_with_session_event(
    context: AdapterContext,
    session: SessionRecord,
    access_token: str,
) -> tuple[
    StudentModelResult,
    TutorResult,
    StudentModelSessionEventResponse | None,
    StudentModelSessionEventResponse | None,
    SessionRecord,
]:
    """Evaluate one answer and apply its authoritative Schema 3.0 event."""

    adapters = get_adapters()
    session = await _initialize_restored_schema_phase(
        session,
        adapters.student_model,
        access_token,
    )
    context = context.model_copy(
        update={
            "question": session.current_question,
            "correct_answer": session.correct_answer,
            "question_number": session.question_number,
        }
    )
    stored_event = session.student_model_event
    if stored_event is None:
        raise HTTPException(
            status_code=409,
            detail="Schema 3.0 session state is required for answer processing.",
        )

    _, student, tutor = await run_tutor_pipeline(context)
    scaffold_turn = session.current_scaffold_step_id is not None
    rules = load_classifier_rules()
    schema_managed = session.current_phase in {
        "GUIDED_PRACTICE",
        "INDEPENDENT_PRACTICE",
    } and (not scaffold_turn or tutor.scaffold_original_answer_correct)
    configured_event = (
        rules.guided_learning.llm_state_mapping[tutor.guided_student_state]
        .student_model_event
        if tutor.guided_student_state is not None
        else None
    )
    event_type: Literal["CORRECT_ATTEMPT", "INCORRECT_ATTEMPT"] | None = (
        "CORRECT_ATTEMPT"
        if configured_event == "CORRECT_ATTEMPT"
        or (configured_event is None and tutor.evaluation == "CORRECT")
        else (
            "INCORRECT_ATTEMPT"
            if configured_event == "INCORRECT_ATTEMPT"
            or (
                configured_event is None
                and tutor.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
            )
            else None
        )
    )
    support_escalation = (
        schema_managed
        and session.current_phase == "GUIDED_PRACTICE"
        and (
            tutor.response_strategy in {"SCAFFOLD", "PROVIDE_WORKED_EXAMPLE"}
            or (
                tutor.intent == "EXPRESSING_CONFUSION"
                and session.stuck_count + 1
                >= rules.strategy_rules.stuck_scaffold_min_count
            )
        )
    )
    if not schema_managed or (event_type is None and not support_escalation):
        return student, tutor, None, None, session

    micro_skill_ids = _schema_event_micro_skills(session)
    retry_required = bool(
        stored_event.journey_state.phase_3_independent_practice
        .retry_required_micro_skill_ids
    )
    if support_escalation:
        escalation_type: Literal[
            "GUIDED_SUPPORT_ESCALATION_REQUIRED",
            "MAXIMUM_GUIDED_SUPPORT_PARALLEL",
        ] = (
            "MAXIMUM_GUIDED_SUPPORT_PARALLEL"
            if tutor.response_strategy == "PROVIDE_WORKED_EXAMPLE"
            else "GUIDED_SUPPORT_ESCALATION_REQUIRED"
        )
        response = await adapters.student_model.send_session_event(
            GuidedSupportEvent(
                request_id=_schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    escalation_type,
                ),
                event_type=escalation_type,
                source_turn_id=context.source_turn_id,
                expected_journey_version=stored_event.journey_state.version,
                topic_id=stored_event.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                question_id=session.question_id,
                micro_skill_id=micro_skill_ids[0],
            ),
            access_token,
        )
    elif session.current_phase == "INDEPENDENT_PRACTICE" and retry_required:
        response = await adapters.student_model.send_session_event(
            IndependentRetryCompletedEvent(
                request_id=_schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    "INDEPENDENT_RETRY_COMPLETED",
                ),
                event_type="INDEPENDENT_RETRY_COMPLETED",
                source_turn_id=context.source_turn_id,
                expected_journey_version=stored_event.journey_state.version,
                topic_id=stored_event.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                question_id=session.question_id,
                micro_skill_ids=micro_skill_ids,
                student_response=context.message,
                independent_success=event_type == "CORRECT_ATTEMPT",
                error_code=(
                    (
                        tutor.selected_error_code
                        if tutor.guided_student_state is not None
                        else _db_error_code(session, context.message) or tutor.error_type
                    )
                    if event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
            ),
            access_token,
        )
    else:
        response = await adapters.student_model.send_session_event(
            GuidedAttemptEvent(
                request_id=_schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    event_type,
                ),
                event_type=event_type,
                source_turn_id=context.source_turn_id,
                expected_journey_version=stored_event.journey_state.version,
                topic_id=stored_event.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                question_id=session.question_id,
                micro_skill_ids=micro_skill_ids,
                student_response=context.message,
                support_used=(
                    _schema_support_used(session, micro_skill_ids)
                    if (
                        session.current_phase == "GUIDED_PRACTICE"
                        and event_type == "CORRECT_ATTEMPT"
                    )
                    else None
                ),
                error_code=(
                    (
                        tutor.selected_error_code
                        if tutor.guided_student_state is not None
                        else _db_error_code(session, context.message) or tutor.error_type
                    )
                    if event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
            ),
            access_token,
        )

    content_response = response
    support_to_serve = (
        response.phase_payload.support_to_serve
        if response.phase_payload is not None
        else None
    )
    logger.info(
        "guided_student_model_event_processed",
        extra={
            "session_id": session.session_id,
            "question_id": session.question_id,
            "student_model_event": (
                "GUIDED_SUPPORT_ESCALATION_REQUIRED"
                if support_escalation
                else event_type
            ),
            "support_type": (
                support_to_serve.get("support_type")
                if support_to_serve is not None
                else None
            ),
            "support_id": (
                support_to_serve.get("support_id")
                if support_to_serve is not None
                else None
            ),
        },
    )

    guided = response.journey_state.phase_2_guided_learning
    if (
        session.current_phase == "GUIDED_PRACTICE"
        and (
            response.routing.next_action == "PROCEED_TO_PHASE_3"
            or (event_type == "CORRECT_ATTEMPT" and not guided.remaining_micro_skill_ids)
        )
    ):
        response = await adapters.student_model.send_session_event(
            GuidedPhaseCompletedEvent(
                request_id=_schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    "GUIDED_PHASE_COMPLETED",
                ),
                event_type="GUIDED_PHASE_COMPLETED",
                source_turn_id=context.source_turn_id,
                expected_journey_version=response.journey_state.version,
                topic_id=response.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                completed_micro_skill_ids=guided.completed_micro_skill_ids,
            ),
            access_token,
        )
    if (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and retry_required
        and response.phase_payload is None
        and response.journey_state.recommended_entry_phase
        == "PHASE_2_GUIDED_LEARNING"
    ):
        response = await adapters.student_model.send_session_event(
            GuidedQuestionSetRequestedEvent(
                request_id=_schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    "GUIDED_QUESTION_SET_REQUESTED",
                ),
                event_type="GUIDED_QUESTION_SET_REQUESTED",
                source_turn_id=context.source_turn_id,
                expected_journey_version=response.journey_state.version,
                topic_id=response.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                target_micro_skill_ids=(
                    response.journey_state.phase_3_independent_practice
                    .unresolved_micro_skill_ids
                ),
            ),
            access_token,
        )
    return (
        student,
        tutor,
        content_response,
        response,
        _apply_schema_event(session, response),
    )


def _student_message_from(request: InteractionRequest) -> str:
    if request.input_source in {"TEXT", "CANVAS"}:
        if request.text_input is None:
            raise HTTPException(
                status_code=422,
                detail=f"text_input is required for {request.input_source} interactions.",
            )
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


def _schema_question(session: SessionRecord) -> StudentModelQuestion:
    event = session.student_model_event
    if event is None:
        raise HTTPException(
            status_code=409,
            detail="Schema 3.0 session state is missing.",
        )
    if event.phase_payload is None or event.phase_payload.question_set is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model returned no active question set.",
        )
    if session.question_id is None:
        raise HTTPException(
            status_code=409,
            detail="The current phase has no active question.",
        )
    question: StudentModelQuestion | None = next(
        (
            item
            for item in event.phase_payload.question_set.questions
            if item.question_id == session.question_id
        ),
        None,
    )
    if question is None:
        raise HTTPException(
            status_code=409,
            detail=f"Student Model did not return metadata for {session.question_id}.",
        )
    return question


def _active_answer_spec(session: SessionRecord) -> AnswerSpec | None:
    if session.student_model_event is None:
        return None
    return _schema_question(session).tutor_view.answer_spec


def _phase_2_prompt_context(
    session: SessionRecord,
) -> Phase2PromptContext | None:
    event = session.student_model_event
    if event is None or session.current_phase != "GUIDED_PRACTICE":
        return None
    question = _schema_question(session)
    guided = event.journey_state.phase_2_guided_learning
    support = (
        event.phase_payload.support_to_serve
        if event.phase_payload is not None
        else None
    )
    return Phase2PromptContext(
        target_micro_skill_ids=guided.current_question_target_micro_skill_ids,
        support_state={
            "highest_support_used_by_skill": guided.highest_support_used_by_skill,
            "completed_micro_skill_ids": guided.completed_micro_skill_ids,
            "remaining_micro_skill_ids": guided.remaining_micro_skill_ids,
        },
        potential_errors=question.tutor_view.potential_errors,
        support_catalog=question.tutor_view.support_catalog,
        current_support=support,
        current_scaffold_step_number=session.scaffold_step_number,
        consecutive_stuck_count=session.stuck_count,
    )


def _db_error_code(session: SessionRecord, student_message: str) -> str | None:
    if session.student_model_event is None:
        return None
    normalized_message = normalize_exact_notation(student_message).casefold()
    for potential_error in _schema_question(session).tutor_view.potential_errors:
        error_code = potential_error.get("error_code")
        response_patterns = potential_error.get("response_patterns")
        if not isinstance(error_code, str) or not isinstance(response_patterns, list):
            continue
        if any(
            isinstance(pattern, str)
            and normalize_exact_notation(pattern).casefold() == normalized_message
            for pattern in response_patterns
        ):
            return error_code
    return None


def _schema_question_mapped_micro_skills(session: SessionRecord) -> list[str]:
    question = _schema_question(session)
    skills = [mapping.micro_skill_id for mapping in question.micro_skill_mappings]
    if not skills:
        raise HTTPException(
            status_code=409,
            detail=f"Student Model returned no micro-skills for {session.question_id}.",
        )
    return skills


def _schema_event_micro_skills(session: SessionRecord) -> list[str]:
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema event skill lookup requires stored journey state.")
    if session.current_phase != "GUIDED_PRACTICE":
        return _schema_question_mapped_micro_skills(session)
    skills = (
        event.journey_state.phase_2_guided_learning
        .current_question_target_micro_skill_ids
    )
    if not skills:
        raise HTTPException(
            status_code=409,
            detail=(
                "Student Model returned no active Phase 2 target micro-skills "
                f"for {session.question_id}."
            ),
        )
    return skills


def _schema_support_used(
    session: SessionRecord,
    micro_skill_ids: list[str],
) -> SupportUsed:
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema support lookup requires a stored Student Model event.")
    support_by_skill = (
        event.journey_state.phase_2_guided_learning.highest_support_used_by_skill
    )
    supports = [support_by_skill.get(skill, "NONE") for skill in micro_skill_ids]
    return max(supports, key=_SUPPORT_RANK.index)


async def _initialize_restored_schema_phase(
    session: SessionRecord,
    student_model: StudentModelAdapter,
    access_token: str,
) -> SessionRecord:
    event = session.student_model_event
    if event is None:
        return session

    payload = event.phase_payload
    if (
        (session.current_question is None or session.question_id is None)
        and payload is not None
        and payload.question_set is not None
        and payload.question_set.questions
    ):
        session = _apply_schema_event(session, event)

    if session.current_phase == "GUIDED_PRACTICE":
        phase_state = event.journey_state.phase_2_guided_learning
        missing_question = session.current_question is None or session.question_id is None
        if phase_state.status != "NOT_STARTED" and not missing_question:
            return session
        target_micro_skill_ids = (
            phase_state.target_micro_skill_ids
            if phase_state.status == "NOT_STARTED"
            else phase_state.remaining_micro_skill_ids
        )
        if not target_micro_skill_ids:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned an active Guided Practice journey "
                    "without a question or remaining target skills."
                ),
            )
        request = GuidedQuestionSetRequestedEvent(
            request_id=(
                f"{session.session_id}:RESTORE-{event.journey_state.version}:"
                "GUIDED_QUESTION_SET_REQUESTED"
            ),
            event_type="GUIDED_QUESTION_SET_REQUESTED",
            source_turn_id=f"RESTORE-{event.journey_state.version}",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            target_micro_skill_ids=target_micro_skill_ids,
        )
    elif session.current_phase == "INDEPENDENT_PRACTICE":
        phase_state = event.journey_state.phase_3_independent_practice
        missing_question = session.current_question is None or session.question_id is None
        if phase_state.status != "NOT_STARTED" and not missing_question:
            return session
        target_micro_skill_ids = (
            phase_state.target_micro_skill_ids
            if phase_state.status == "NOT_STARTED"
            else phase_state.remaining_micro_skill_ids
        )
        if not target_micro_skill_ids:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Student Model returned an active Independent Practice journey "
                    "without a question or remaining target skills."
                ),
            )
        support_by_skill = (
            event.journey_state.phase_2_guided_learning.highest_support_used_by_skill
        )
        request = IndependentQuestionSetRequestedEvent(
            request_id=(
                f"{session.session_id}:RESTORE-{event.journey_state.version}:"
                "INDEPENDENT_QUESTION_SET_REQUESTED"
            ),
            event_type="INDEPENDENT_QUESTION_SET_REQUESTED",
            source_turn_id=f"RESTORE-{event.journey_state.version}",
            expected_journey_version=event.journey_state.version,
            topic_id=event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            phase2_repair_results=[
                Phase2RepairResult(
                    micro_skill_id=micro_skill_id,
                    highest_support_used=support_by_skill.get(micro_skill_id, "NONE"),
                )
                for micro_skill_id in target_micro_skill_ids
            ],
            used_question_ids=phase_state.used_question_ids,
        )
    else:
        return session

    response = await student_model.send_session_event(request, access_token)
    payload = response.phase_payload
    effective_phase = (
        response.journey_state.recommended_entry_phase
        or response.journey_state.current_phase
    )
    initialized_state = (
        response.journey_state.phase_2_guided_learning
        if session.current_phase == "GUIDED_PRACTICE"
        else response.journey_state.phase_3_independent_practice
    )
    if (
        payload is None
        or PHASE_FROM_STUDENT_MODEL[payload.phase] != session.current_phase
        or payload.phase != effective_phase
        or payload.payload_type != "QUESTION_SET"
        or payload.question_set is None
        or not payload.question_set.questions
        or initialized_state.status == "NOT_STARTED"
    ):
        raise HTTPException(
            status_code=503,
            detail="Student Model did not initialize the restored phase with questions.",
        )
    return _apply_schema_event(session, response)
def _schema_visual_cue(
    event: StudentModelSessionEventResponse | None,
) -> VisualCue | None:
    if event is None or event.phase_payload is None:
        return None
    support = event.phase_payload.support_to_serve
    if support is None:
        return None
    items = support.get("items")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or item.get("content_type") != "VISUAL_CUE":
            continue
        content_id = item.get("content_id")
        description = item.get("description")
        actions = item.get("actions", [])
        if not isinstance(content_id, str) or not isinstance(description, str):
            raise RuntimeError("Student Model returned a malformed visual cue.")
        if not isinstance(actions, list) or not all(
            isinstance(action, dict) for action in actions
        ):
            raise RuntimeError("Student Model returned malformed visual cue actions.")
        return VisualCue(
            show=True,
            cue_type=content_id,
            description=description,
            actions=actions,
        )
    return None


def _schema_hint(event: StudentModelSessionEventResponse | None) -> str | None:
    if event is None or event.phase_payload is None:
        return None
    support = event.phase_payload.support_to_serve
    items = support.get("items") if support is not None else None
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get("content_type") == "HINT":
            content = item.get("content")
            return content if isinstance(content, str) else None
    return None


def _contextual_schema_hint(
    schema_hint: str | None,
    tutor_message: str,
) -> str:
    if schema_hint is None:
        return tutor_message
    if normalize_exact_notation(schema_hint).casefold() in (
        normalize_exact_notation(tutor_message).casefold()
    ):
        return tutor_message
    return f"{tutor_message.rstrip()} {schema_hint}"


def _schema_support_steps(
    event: StudentModelSessionEventResponse | None,
) -> list[str]:
    if event is None or event.phase_payload is None:
        return []
    support = event.phase_payload.support_to_serve
    if support is not None:
        current_prompt = support.get("prompt")
        if isinstance(current_prompt, str):
            return [current_prompt]
        current_step_id = support.get("current_step_id")
        steps = support.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if current_step_id is not None and step.get("step_id") != current_step_id:
                    continue
                prompt = step.get("prompt")
                if isinstance(prompt, str):
                    return [prompt]
                if current_step_id is not None:
                    break
    # Rescue catalogues contain final answers and future teaching steps. They stay
    # private until the dedicated parallel/tutor-solved conversation is active.
    return []


def _validate_scaffold_prompt(
    prompt: str,
    correct_answer: str | None,
    rules: ClassifierRulesConfig,
) -> None:
    if (
        correct_answer is not None
        and contains_answer_reveal(prompt, correct_answer, rules)
    ):
        raise RuntimeError(
            "Student Model scaffold prompt reveals the original canonical answer."
        )


def _schema_scaffold_state(
    event: StudentModelSessionEventResponse | None,
) -> dict[str, object]:
    if event is None or event.phase_payload is None:
        return {}
    support = event.phase_payload.support_to_serve
    if support is None or support.get("support_type") != "SCAFFOLD":
        return {}
    scaffold_id = support.get("scaffold_id")
    current_step_id = support.get("current_step_id")
    expected_response = support.get("expected_response")
    steps = support.get("steps")
    step_number = 0
    if isinstance(steps, list):
        for index, step in enumerate(steps, start=1):
            if isinstance(step, dict) and step.get("step_id") == current_step_id:
                step_number = index
                if expected_response is None:
                    expected_response = step.get("expected_response")
                break
    delivered = [current_step_id] if isinstance(current_step_id, str) else []
    return {
        "scaffold_id": scaffold_id if isinstance(scaffold_id, str) else None,
        "current_scaffold_step_id": (
            current_step_id if isinstance(current_step_id, str) else None
        ),
        "scaffold_step_number": step_number,
        "scaffold_total_steps": len(steps) if isinstance(steps, list) else 0,
        "delivered_scaffold_step_ids": delivered,
        "scaffold_expected_response": (
            expected_response if isinstance(expected_response, str) else None
        ),
    }


def _active_scaffold_steps(session: SessionRecord) -> list[dict[str, object]]:
    event = session.student_model_event
    if event is None or event.phase_payload is None:
        return []
    support = event.phase_payload.support_to_serve
    if support is None or support.get("support_type") != "SCAFFOLD":
        return []
    steps = support.get("steps")
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _next_scaffold_state(
    session: SessionRecord,
) -> tuple[str | None, dict[str, object]]:
    steps = _active_scaffold_steps(session)
    current_step_id = session.current_scaffold_step_id
    for index, step in enumerate(steps):
        if step.get("step_id") != current_step_id:
            continue
        delivered = (
            [*session.delivered_scaffold_step_ids, current_step_id]
            if (
                isinstance(current_step_id, str)
                and current_step_id not in session.delivered_scaffold_step_ids
            )
            else session.delivered_scaffold_step_ids
        )
        if index + 1 == len(steps):
            return None, {
                "scaffold_id": None,
                "current_scaffold_step_id": None,
                "scaffold_step_number": 0,
                "scaffold_total_steps": 0,
                "delivered_scaffold_step_ids": delivered,
                "scaffold_expected_response": None,
            }
        next_step = steps[index + 1]
        next_id = next_step.get("step_id")
        prompt = next_step.get("prompt")
        expected = next_step.get("expected_response")
        if not isinstance(next_id, str) or not isinstance(prompt, str):
            raise RuntimeError("Student Model returned a malformed scaffold step.")
        return prompt, {
            "scaffold_id": session.scaffold_id,
            "current_scaffold_step_id": next_id,
            "scaffold_step_number": index + 2,
            "scaffold_total_steps": len(steps),
            "delivered_scaffold_step_ids": delivered,
            "scaffold_expected_response": (
                expected if isinstance(expected, str) else None
            ),
        }
    raise RuntimeError(
        f"Current scaffold step {current_step_id} is absent from its catalogue."
    )


def _completed_scaffold_state(session: SessionRecord) -> dict[str, object]:
    delivered = list(session.delivered_scaffold_step_ids)
    if (
        session.current_scaffold_step_id is not None
        and session.current_scaffold_step_id not in delivered
    ):
        delivered.append(session.current_scaffold_step_id)
    return {
        "scaffold_id": None,
        "current_scaffold_step_id": None,
        "scaffold_step_number": 0,
        "scaffold_total_steps": 0,
        "delivered_scaffold_step_ids": delivered,
        "scaffold_expected_response": None,
    }


def _scaffold_response_is_correct(
    student_message: str,
    expected_response: str,
    tutor_evaluation: str,
    rules: ClassifierRulesConfig,
) -> bool:
    normalized_student = _normalize_scaffold_response(student_message)
    normalized_expected = _normalize_scaffold_response(expected_response)
    aliases = next(
        (
            values
            for key, values in rules.scaffold_response_rules.aliases.items()
            if _normalize_scaffold_response(key) == normalized_expected
        ),
        [],
    )
    accepted = {
        normalized_expected,
        *(_normalize_scaffold_response(alias) for alias in aliases),
    }
    if any(_contains_scaffold_response(normalized_student, value) for value in accepted):
        return True
    return tutor_evaluation == "CORRECT"


def _scaffold_evaluation_context(
    session: SessionRecord,
) -> ScaffoldEvaluationContext:
    if (
        session.scaffold_id is None
        or session.current_scaffold_step_id is None
        or session.current_question is None
        or session.correct_answer is None
        or session.scaffold_expected_response is None
        or not session.scaffold_steps
    ):
        raise RuntimeError("Active scaffold is missing evaluation context.")
    answer_spec = _active_answer_spec(session)
    return ScaffoldEvaluationContext(
        scaffold_id=session.scaffold_id,
        step_id=session.current_scaffold_step_id,
        original_question=session.current_question,
        canonical_answer=session.correct_answer,
        accepted_answers=(
            answer_spec.accepted_answers
            if answer_spec is not None
            else []
        ),
        verification_method=(
            answer_spec.verification_method
            if answer_spec is not None
            else None
        ),
        step_prompt=session.scaffold_steps[0],
        expected_response_criterion=session.scaffold_expected_response,
        completed_step_ids=session.delivered_scaffold_step_ids,
    )


def _normalize_scaffold_response(value: str) -> str:
    normalized = value.casefold().replace("−", "-").replace("⁄", "/")
    normalized = re.sub(r"(?<=[\d½⅓¼¾⅔⅛])(?=[a-z])", " ", normalized)
    normalized = re.sub(r"(?<=[a-z])(?=[\d½⅓¼¾⅔⅛])", " ", normalized)
    normalized = re.sub(r"[^\w/½⅓¼¾⅔⅛]+", " ", normalized)
    return " ".join(normalized.split())


def _contains_scaffold_response(student: str, expected: str) -> bool:
    if expected == "":
        return False
    pattern = rf"(?<![\w/]){re.escape(expected)}(?![\w/])"
    return re.search(pattern, student) is not None


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


def _next_hint_count_from(session: SessionRecord) -> int:
    return session.hint_count


def _new_tutor_turn_id() -> str:
    return f"TUTOR-{uuid4()}"


def _schema_interaction_request_id(
    session: SessionRecord,
    source_turn_id: str,
    event_type: str,
) -> str:
    return f"{session.session_id}:{source_turn_id}:{event_type}"


def _turn_updates(
    request: InteractionRequest,
    last_tutor_action: TutorAction,
    expected_student_response: ExpectedStudentResponse,
) -> dict[str, object]:
    updates: dict[str, object] = {
        "last_tutor_action": last_tutor_action,
        "expected_student_response": expected_student_response,
    }
    if request.turn_id is None:
        raise RuntimeError("validated interaction is missing turn_id")
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
        request.turn_id is None
        or request.turn_id != session.last_processed_turn_id
    ):
        return None
    response = last_interaction_response_for(session.session_id, request.turn_id)
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
    return (
        (
            request.previous_tutor_turn_id is not None
            and request.previous_tutor_turn_id != session.last_tutor_turn_id
        )
        or (
            session.question_id is not None
            and request.question_id != session.question_id
        )
    )


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
    stored_event = session.student_model_event
    guided = (
        stored_event.journey_state.phase_2_guided_learning
        if stored_event is not None
        else None
    )
    support = (
        stored_event.phase_payload.support_to_serve
        if stored_event is not None and stored_event.phase_payload is not None
        else None
    )
    support_type = support.get("support_type") if support is not None else None
    active_support_level = (
        support_type
        if support_type in _SUPPORT_RANK
        else "VISUAL_CUE"
        if support_type == "HINT_AND_VISUAL_CUE"
        else "NONE"
    )
    highest_support_used = (
        max(
            guided.highest_support_used_by_skill.values(),
            key=_SUPPORT_RANK.index,
            default="NONE",
        )
        if guided is not None
        else "NONE"
    )
    active_objective = session.active_teaching_objective
    return InteractionResponse(
        session_id=request.session_id,
        student_id=request.student_id,
        status=status,
        accepted_turn_id=session.last_processed_turn_id,
        interaction_state_version=session.interaction_state_version,
        tutor_turn_id=session.last_tutor_turn_id,
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
        question_type=session.question_type,
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
        scaffold_id=session.scaffold_id,
        current_scaffold_step_id=session.current_scaffold_step_id,
        scaffold_step_number=session.scaffold_step_number,
        scaffold_step_text=scaffold_steps[0] if scaffold_steps else None,
        scaffold_step_voice=scaffold_steps[0] if scaffold_steps else None,
        total_scaffold_steps=session.scaffold_total_steps,
        allow_text_input=session.allow_text_input,
        allow_voice_input=session.allow_voice_input,
        hint_count=session.hint_count,
        attempt_count=session.attempt_count,
        question_completed=session.question_completed,
        answer_value_confirmed=session.answer_value_confirmed,
        phase_indicator=session.current_phase,
        recommended_entry_phase=session.recommended_entry_phase,
        session_summary=session_summary,
        student_model_event=session.student_model_event,
        student_model_state=session.student_model_state,
        active_teaching_objective=active_objective,
        first_unresolved_concept_id=(
            active_objective.missing_concept_ids[0]
            if active_objective is not None
            and active_objective.missing_concept_ids
            else None
        ),
        active_support_level=active_support_level,
        highest_support_used=highest_support_used,
        consecutive_stuck_count=session.stuck_count,
        active_scaffold=(
            {
                "scaffold_id": session.scaffold_id,
                "current_step_id": session.current_scaffold_step_id,
                "step_number": session.scaffold_step_number,
                "total_steps": session.scaffold_total_steps,
                "step_text": session.scaffold_steps[0],
                "step_voice": session.scaffold_steps[0],
            }
            if session.scaffold_id is not None
            and session.current_scaffold_step_id is not None
            and session.scaffold_step_number > 0
            and session.scaffold_total_steps > 0
            and session.scaffold_steps
            else None
        ),
    )


def _cache_response(
    request: InteractionRequest,
    response: InteractionResponse,
) -> InteractionResponse:
    if request.turn_id is None:
        raise RuntimeError("validated interaction is missing turn_id")
    cache_interaction_response(request.session_id, request.turn_id, response)
    return response


async def process_interaction(
    request: InteractionRequest,
    access_token: str,
) -> InteractionResponse | StaleTurnResponse:
    async with interaction_lock_for(request.session_id):
        response = await _process_interaction(request, access_token)
    logger.info(
        "interaction_turn_completed",
        extra={
            "session_id": request.session_id,
            "turn_id": request.turn_id,
            "input_source": request.input_source,
            "interaction_type": request.interaction_type,
            "status": response.status,
            "state_version": getattr(response, "interaction_state_version", None),
        },
    )
    return response


def _active_support_message(session: SessionRecord) -> str | None:
    event = session.student_model_event
    if event is None:
        return None
    steps = _schema_support_steps(event)
    if steps:
        return steps[0]
    return _schema_hint(event)


def _non_graded_response(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
    conversation_action: ConversationAction,
) -> InteractionResponse:
    state_updates = _turn_updates(request, "GAVE_HINT", "ANSWER")
    if request.interaction_type == "INACTIVITY_NUDGE":
        state_updates["nudge_generated_count"] = session.nudge_generated_count + 1
    if request.interaction_type == "NUDGE_PRESENTED":
        state_updates["nudge_presented_count"] = session.nudge_presented_count + 1
    updated_session = update_interaction_state(
        request.session_id,
        request.student_id,
        session,
        session.current_phase,
        session.hint_count,
        session.current_phase,
        request.transcript_confidence,
        request.canvas_snapshot_id,
        None,
        session.show_visual_cue,
        session.show_scaffold_panel,
        session.scaffold_steps,
        state_updates,
    )
    return _cache_response(
        request,
        _response_from(
            request,
            updated_session,
            message,
            message,
            None,
            updated_session.scaffold_steps,
            None,
            conversation_action,
            0,
            None,
            True,
        ),
    )


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

    if request.interaction_type in {"HELP_REQUEST", "SUPPORT_REPLAY"}:
        support_message = _active_support_message(session)
        if support_message is None:
            raise HTTPException(
                status_code=409,
                detail="NO_ACTIVE_SUPPORT: this session has no support to replay.",
            )
        return _non_graded_response(
            request,
            session,
            support_message,
            "GIVE_HINT",
        )
    if request.interaction_type == "INACTIVITY_NUDGE":
        if session.nudge_generated_count >= 4:
            raise HTTPException(
                status_code=429,
                detail="INACTIVITY_NUDGE generation limit reached for this tutor turn.",
            )
        return _non_graded_response(
            request,
            session,
            "Are you still with me? Take your time and continue when you're ready.",
            "WAIT_FOR_STUDENT",
        )
    if request.interaction_type == "NUDGE_PRESENTED":
        if session.nudge_presented_count >= 2:
            raise HTTPException(
                status_code=429,
                detail="INACTIVITY_NUDGE presentation limit reached for this tutor turn.",
            )
        return _non_graded_response(
            request,
            session,
            "Take your time and continue when you're ready.",
            "WAIT_FOR_STUDENT",
        )

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
            session,
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
                **_turn_updates(
                    request,
                    "REQUESTED_CLARIFICATION",
                    "CLARIFICATION",
                ),
            },
        )
        return _cache_response(
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

    adapters = get_adapters()
    if (
        session.student_model_event is not None
        and session.current_phase in {"GUIDED_PRACTICE", "INDEPENDENT_PRACTICE"}
        and request.interaction_type == "ANSWER_SUBMISSION"
    ):
        session = await _initialize_restored_schema_phase(
            session,
            adapters.student_model,
            access_token,
        )

    if session.current_question is None or session.question_id is None:
        raise HTTPException(
            status_code=409,
            detail="The current phase has no active question.",
        )

    turn_session = session
    recent_history: list[ConversationMessage] = _recent_conversation_history(
        session.conversation_history,
        rules.conversation_rules.max_recent_messages,
    )
    canvas_submission = get_canvas_submission(session, request.canvas_snapshot_id)
    ocr = canvas_submission.ocr if canvas_submission is not None else None
    scaffold_turn = (
        request.interaction_type == "ANSWER_SUBMISSION"
        and session.current_scaffold_step_id is not None
    )
    if scaffold_turn and session.scaffold_expected_response is None:
        raise RuntimeError(
            f"Scaffold step {session.current_scaffold_step_id} has no expected response."
        )

    detected_intent = detect_student_intent(student_message, rules)
    next_attempt_count = (
        session.attempt_count
        + (
            session.stuck_count + 1
            if detected_intent == "EXPRESSING_CONFUSION"
            else 1
        )
        if (
            request.interaction_type == "ANSWER_SUBMISSION"
            and not session.answer_value_confirmed
        )
        else session.attempt_count
    )
    context = AdapterContext(
        session_id=request.session_id,
        student_id=request.student_id,
        source_turn_id=request.turn_id,
        question_id=session.question_id,
        question_type=None if scaffold_turn else session.question_type,
        message=student_message,
        question=(
            session.scaffold_steps[0]
            if scaffold_turn and session.scaffold_steps
            else session.current_question
        ),
        # Grade against the session's question: after a 6.7 transition swaps
        # the question, the request's id from the frontend may be stale.
        correct_answer=(
            session.scaffold_expected_response
            if scaffold_turn
            else session.correct_answer
        ),
        answer_spec=None if scaffold_turn else _active_answer_spec(session),
        phase_2_prompt_context=_phase_2_prompt_context(session),
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
        generated_question_rubric=session.generated_question_rubric,
        active_teaching_objective=session.active_teaching_objective,
        scaffold_evaluation_context=(
            _scaffold_evaluation_context(session)
            if scaffold_turn
            else None
        ),
        detected_equation=ocr.detected_equation if ocr is not None else None,
        detected_steps=ocr.detected_steps if ocr is not None else [],
        ocr_confidence=ocr.confidence if ocr is not None else None,
        canvas_regions=ocr.detected_regions if ocr is not None else [],
    )
    safety_check = await adapters.safety.check(context)
    if not safety_check.passed:
        fallback = safety_check.safe_fallback_message or "Let's pause for a moment."
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session,
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
                **_turn_updates(
                    request,
                    session.last_tutor_action,
                    session.expected_student_response,
                ),
            },
        )
        return _cache_response(
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

    schema_session = session.student_model_event is not None
    if schema_session and request.interaction_type == "ANSWER_SUBMISSION":
        (
            student,
            tutor,
            schema_content_response,
            schema_response,
            session,
        ) = await process_answer_with_session_event(context, session, access_token)
    else:
        _, student, tutor = await run_tutor_pipeline(context)
        schema_content_response = None
        schema_response = None
    tutor = tutor.model_copy(update={"safety_check": safety_check})

    visual_cue = _schema_visual_cue(schema_content_response) or (
        tutor.visual_cue if tutor.visual_cue.show else None
    )
    schema_hint = _schema_hint(schema_content_response)
    schema_steps = _schema_support_steps(schema_content_response)
    for scaffold_prompt in schema_steps:
        _validate_scaffold_prompt(scaffold_prompt, session.correct_answer, rules)
    scaffold_steps = schema_steps or tutor.scaffold_steps_delivered
    tutor_message = _contextual_schema_hint(schema_hint, tutor.tutor_message)
    tutor_message_voice = _contextual_schema_hint(
        schema_hint,
        tutor.tutor_message_voice,
    )
    if schema_steps:
        tutor_message = schema_steps[0]
        tutor_message_voice = schema_steps[0]
    scaffold_turn_updates: dict[str, object] = {}
    if scaffold_turn and tutor.scaffold_original_answer_correct:
        scaffold_steps = []
        scaffold_turn_updates = _completed_scaffold_state(turn_session)
    elif scaffold_turn:
        expected_scaffold_response = turn_session.scaffold_expected_response
        if expected_scaffold_response is None:
            raise RuntimeError("Active scaffold step lost its expected response.")
        if _scaffold_response_is_correct(
            student_message,
            expected_scaffold_response,
            tutor.evaluation,
            rules,
        ):
            next_prompt, scaffold_turn_updates = _next_scaffold_state(turn_session)
            if next_prompt is None:
                tutor_message = rules.messages.SCAFFOLD_ORIGINAL_RETRY
                tutor_message_voice = tutor_message
                scaffold_steps = []
            else:
                _validate_scaffold_prompt(
                    next_prompt,
                    turn_session.correct_answer,
                    rules,
                )
                tutor_message = next_prompt
                tutor_message_voice = next_prompt
                scaffold_steps = [next_prompt]
        else:
            scaffold_steps = list(turn_session.scaffold_steps)
            if not scaffold_steps:
                raise RuntimeError("Active scaffold step lost its prompt.")
            tutor_message = rules.messages.SCAFFOLD_STEP_RETRY.format(
                step=scaffold_steps[0]
            )
            tutor_message_voice = tutor_message
    conversation_history: list[ConversationMessage] = _updated_conversation_history(
        turn_session.conversation_history,
        student_message,
        tutor_message,
        rules.conversation_rules.max_recent_messages,
    )

    effective_attempt_increment: int = (
        0
        if scaffold_turn and not tutor.scaffold_original_answer_correct
        else tutor.attempt_increment
        if request.interaction_type == "ANSWER_SUBMISSION"
        else 0
    )
    completed: bool = (
        tutor.question_completed
        if request.interaction_type == "ANSWER_SUBMISSION"
        else session.question_completed
    )
    applied_attempt_count: int = session.attempt_count + effective_attempt_increment
    recommended: str | None = session.recommended_entry_phase
    new_phase: Phase | None = (
        session.current_phase
        if schema_response is not None
        and session.current_phase != turn_session.current_phase
        else None
    )
    logger.info(
        "phase_transition_evaluated",
        extra={
            "session_id": session.session_id,
            "current_phase": turn_session.current_phase,
            "student_model_recommended_phase": recommended,
            "phase_changed": new_phase is not None,
            "attempt_count": applied_attempt_count,
        },
    )

    next_hint_count: int = _next_hint_count_from(session)
    conversation_action: ConversationAction = tutor.recommended_conversation_action
    # Persisted every turn: the real attempt counter and completion state Sanya
    # reads back on the next turn.
    schema_question_changed = (
        schema_response is not None and session.question_id != turn_session.question_id
    )
    state_updates: dict[str, object] = {
        "interaction_state_version": session.interaction_state_version + 1,
        "nudge_generated_count": 0,
        "nudge_presented_count": 0,
        "attempt_count": (
            session.attempt_count if schema_question_changed else applied_attempt_count
        ),
        "question_completed": (
            session.question_completed if schema_question_changed else completed
        ),
        "answer_value_confirmed": (
            session.answer_value_confirmed
            if schema_question_changed
            else tutor.answer_value_confirmed
        ),
        "conversation_history": conversation_history,
        "generated_question_rubric": (
            tutor.generated_question_rubric
            if tutor.generated_question_rubric is not None
            else session.generated_question_rubric
        ),
        "active_teaching_objective": (
            tutor.active_teaching_objective
            if tutor.guided_student_state is not None
            else session.active_teaching_objective
        ),
        "recommended_entry_phase": recommended,
        "stuck_count": (
            session.stuck_count + 1
            if tutor.intent == "EXPRESSING_CONFUSION"
            else (
                0
                if request.interaction_type == "ANSWER_SUBMISSION"
                else session.stuck_count
            )
        ),
        **_schema_scaffold_state(schema_content_response),
        **scaffold_turn_updates,
    }
    if scaffold_turn and not tutor.scaffold_original_answer_correct:
        conversation_action = "ASK_QUESTION"
        state_updates.update(
            {
                "question_completed": False,
                "answer_value_confirmed": False,
            }
        )
    if schema_question_changed:
        state_updates["stuck_count"] = 0
        state_updates["generated_question_rubric"] = None
        state_updates["active_teaching_objective"] = None
        state_updates["explanation_request_count"] = 0

    # A rejected explanation must not loop forever. The evaluator accepts
    # concrete wordings ("I subtracted 6 from both sides") but can reject a
    # child's generic-but-honest ones ("I moved it to the other side") — and
    # PARTIAL turns carry attempt_increment=0, so no counter ever advanced and
    # no support ever escalated. Live on 31 Jul: 29 consecutive
    # REQUEST_EXPLANATION turns on one question; the session was unwinnable.
    # After two rejected asks the third would start the loop, so accept the
    # student's reasoning and move on — the answer VALUE was already right, and
    # the question_advanced block below supplies the next-question message.
    # Schema-managed turns are untouched: there the Student Model owns
    # progression.
    if conversation_action == "REQUEST_EXPLANATION" and schema_response is None:
        if session.explanation_request_count >= 2:
            conversation_action = "ADVANCE_TO_NEXT_QUESTION"
            state_updates["explanation_request_count"] = 0
            state_updates["question_completed"] = True
        else:
            state_updates["explanation_request_count"] = (
                session.explanation_request_count + 1
            )
    elif session.explanation_request_count:
        state_updates["explanation_request_count"] = 0
    if schema_response is None:
        state_updates["last_student_model"] = student
    if (
        request.interaction_type == "ANSWER_SUBMISSION"
        and (not scaffold_turn or tutor.scaffold_original_answer_correct)
        and effective_attempt_increment == 1
    ):
        state_updates["per_question_history"] = [
            *session.per_question_history,
            QuestionAttemptRecord(
                question_id=turn_session.question_id,
                question_text=turn_session.current_question,
                phase=turn_session.current_phase,
                evaluation=tutor.evaluation,
                error_type=tutor.error_type if tutor.evaluation != "CORRECT" else None,
                input_source=request.input_source,
                hint_level_used=tutor.hint_level,
                attempted_at=datetime.now(timezone.utc),
            ),
        ]
    resulting_question_id = state_updates.get("question_id", session.question_id)
    resulting_question = state_updates.get(
        "current_question",
        session.current_question,
    )
    question_advanced = (
        isinstance(resulting_question_id, str)
        and resulting_question_id != turn_session.question_id
        and isinstance(resulting_question, str)
        and resulting_question.strip() != ""
    )
    if question_advanced:
        tutor_message = rules.messages.NEXT_QUESTION.format(
            question=resulting_question.strip()
        )
        tutor_message_voice = tutor_message
        conversation_action = "ADVANCE_TO_NEXT_QUESTION"
        state_updates["conversation_history"] = [
            ConversationMessage(role="assistant", content=tutor_message)
        ]

    resulting_question_completed: bool = bool(
        state_updates.get("question_completed", completed)
    )
    last_tutor_action, expected_student_response = _conversation_state_for(
        conversation_action,
        resulting_question_completed,
        tutor.evaluation,
    )
    state_updates.update(
        _turn_updates(
            request,
            last_tutor_action,
            expected_student_response,
        )
    )

    next_phase = session.current_phase
    updated_session = update_interaction_state(
        request.session_id,
        request.student_id,
        session,
        next_phase,
        next_hint_count,
        next_phase,
        request.transcript_confidence,
        request.canvas_snapshot_id,
        None,
        visual_cue is not None,
        len(scaffold_steps) > 0,
        scaffold_steps,
        state_updates,
    )

    return _cache_response(
        request,
        _response_from(
            request,
            updated_session,
            tutor_message,
            tutor_message_voice,
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
