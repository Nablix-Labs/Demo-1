"""Accepted Student Turn evaluation and authoritative state advancement.

Extracts the shared evaluation nucleus used by text, voice, and Canvas turns.
Evaluates answers, runs the tutor pipeline, applies Student Model events,
and routes support/prerequisite escalations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Literal

from fastapi import HTTPException

from app.adapters.base import StudentModelAdapter, TutorEngineAdapter
from app.adapters.provider import get_adapters
from app.ai_engine.classifier import (
    normalize_exact_notation,
    selected_option_submission,
)
from app.ai_engine.classifier_config import (
    ClassifierRulesConfig,
    load_classifier_rules,
)
from app.core.config import get_settings
from app.core.logger import logger
from app.models.adapters import (
    AdapterContext,
    StudentModelResult,
    TutorResult,
)
from app.models.guided_learning import (
    EvaluationReasonCode,
    WrongEscalationCode,
)
from app.models.remediation import Phase3Checkpoint
from app.models.session import SessionRecord
from app.models.student_model_session import (
    FreshIndependentQuestionRequestedEvent,
    GuidedAttemptEvent,
    GuidedQuestionSetRequestedEvent,
    GuidedSupportEvent,
    IndependentRetryCompletedEvent,
    PrerequisiteRouteResolvedEvent,
    StudentModelSessionEventResponse,
    SupportUsed,
)
from app.services.canvas_annotations import plan_rescue_canvas_actions
from app.services.canvas_evidence import canvas_submission_is_pending
from app.services.journey_lifecycle import initialize_restored_schema_phase
from app.services.rescue_presentation import (
    guided_rescue,
    presented_rescue,
    rescue_context_for,
    scaffold_response_is_correct,
    tutor_with_guided_rescue,
)
from app.services.session_service import (
    _apply_schema_event,
    _authoritative_intervention,
    complete_guided_progression,
    require_learning_active,
    store_pending_support_event,
    store_prerequisite_repair_event,
)
from app.services.student_model_session import (
    schema_event_micro_skills,
    schema_question,
    schema_support_used,
)

_EVALUATION_REASON_BY_STATE: dict[str, EvaluationReasonCode] = {
    "CORRECT": EvaluationReasonCode.ALL_REQUIRED_COMPONENTS_CONFIRMED,
    "PARTIAL": EvaluationReasonCode.REQUIRED_COMPONENTS_MISSING,
    "WRONG": EvaluationReasonCode.RESPONSE_INCORRECT,
    "STUCK": EvaluationReasonCode.STUDENT_STUCK,
    "UNCLEAR": EvaluationReasonCode.RESPONSE_UNCLEAR,
}
_WRONG_ESCALATION_BY_COUNT: dict[int, WrongEscalationCode] = {
    1: WrongEscalationCode.WRONG_1_HINT,
    2: WrongEscalationCode.WRONG_2_HINT,
    3: WrongEscalationCode.WRONG_3_VISUAL_CUE,
    4: WrongEscalationCode.WRONG_4_INTERVENTION,
}


@dataclass(frozen=True)
class StudentTurnResult:
    """The strictly typed result of evaluating an accepted student turn."""
    student_model_result: StudentModelResult
    tutor_result: TutorResult
    content_event: StudentModelSessionEventResponse | None
    applied_event: StudentModelSessionEventResponse | None
    session: SessionRecord


def evaluation_reason(tutor: TutorResult) -> EvaluationReasonCode:
    if tutor.guided_student_state is not None:
        return _EVALUATION_REASON_BY_STATE[tutor.guided_student_state]
    if tutor.evaluation == "CORRECT":
        return EvaluationReasonCode.ALL_REQUIRED_COMPONENTS_CONFIRMED
    if tutor.evaluation == "PARTIALLY_CORRECT":
        return EvaluationReasonCode.REQUIRED_COMPONENTS_MISSING
    if tutor.evaluation == "INCORRECT":
        return EvaluationReasonCode.RESPONSE_INCORRECT
    return EvaluationReasonCode.RESPONSE_UNCLEAR


async def run_tutor_pipeline(
    context: AdapterContext,
    student_model: StudentModelAdapter | None = None,
    tutor_engine: TutorEngineAdapter | None = None,
) -> tuple[StudentModelResult, TutorResult]:
    """Run the shared student-model and tutor-engine adapter sequence."""
    adapters = get_adapters()
    sm = student_model or adapters.student_model
    te = tutor_engine or adapters.tutor
    student = await sm.assess(context)
    tutor = await te.evaluate(context, student)
    return student, tutor


import inspect


async def _invoke_tutor_pipeline(
    pipeline,
    context: AdapterContext,
    sm: StudentModelAdapter | None,
    te: TutorEngineAdapter | None,
) -> tuple[StudentModelResult, TutorResult]:
    sig = inspect.signature(pipeline)
    accepts_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    kwargs = {}
    if accepts_kwargs or "student_model" in sig.parameters:
        kwargs["student_model"] = sm
    if accepts_kwargs or "tutor_engine" in sig.parameters:
        kwargs["tutor_engine"] = te
    return await pipeline(context, **kwargs)


def require_authored_canvas_confirmation(
    session: SessionRecord,
    tutor: TutorResult,
    canvas_submission_complete: bool,
) -> TutorResult:
    """Keep configured guided-rule questions open until canvas work is checked."""
    if (
        not session.canvas_submission_required
        or canvas_submission_complete
        or tutor.requires_written_math_evidence
    ):
        return tutor
    if not tutor.answer_value_confirmed:
        return tutor
    rules = load_classifier_rules()
    instruction = rules.guided_learning.critical_thinking.written_rule_prompt
    message = (
        tutor.tutor_message
        if canvas_submission_is_pending(session)
        else f"{tutor.tutor_message.rstrip()} {instruction}"
    )
    return tutor.model_copy(
        update={
            "evaluation": "PARTIALLY_CORRECT",
            "response_strategy": "CLARIFY",
            "tutor_message": message,
            "tutor_message_voice": message,
            "attempt_increment": 0,
            "recommended_conversation_action": "REQUEST_CLARIFICATION",
            "question_completed": False,
            "reasoning_complete": False,
            "requires_written_math_evidence": True,
            "write_instruction": instruction,
        }
    )


def is_wrong_evaluation(tutor: TutorResult) -> bool:
    if tutor.contribution is not None:
        return tutor.contribution.assessment == "INCORRECT"
    return (
        tutor.guided_student_state == "WRONG"
        or (
            tutor.evaluation == "INCORRECT"
            and tutor.intent != "EXPRESSING_CONFUSION"
        )
    )


def is_support_failure(tutor: TutorResult) -> bool:
    """Return whether an unresolved answer should advance guided support."""
    return is_wrong_evaluation(tutor)


def is_unresolved_scaffold_turn(tutor: TutorResult) -> bool:
    """Return whether a scaffold step needs a more supportive representation."""
    return is_wrong_evaluation(tutor) if tutor.contribution is not None else tutor.intent != "ASKING_QUESTION"


def guided_attempt_event_type(
    tutor: TutorResult,
    rules: ClassifierRulesConfig,
) -> Literal["CORRECT_ATTEMPT", "INCORRECT_ATTEMPT"] | None:
    """Map every answer that advances support to an authoritative attempt event."""
    if tutor.contribution is not None:
        if tutor.contribution.assessment == "INCORRECT":
            return "INCORRECT_ATTEMPT"
        if tutor.contribution.assessment == "CORRECT" and tutor.evaluation == "CORRECT":
            return "CORRECT_ATTEMPT"
        return None
    configured_event = (
        rules.guided_learning.llm_state_mapping[tutor.guided_student_state]
        .student_model_event
        if tutor.guided_student_state is not None
        else None
    )
    if configured_event == "CORRECT_ATTEMPT" or (
        configured_event is None and tutor.evaluation == "CORRECT"
    ):
        return "CORRECT_ATTEMPT"
    if (
        configured_event == "INCORRECT_ATTEMPT"
        or is_support_failure(tutor)
        or (
            tutor.guided_student_state is None
            and configured_event is None
            and tutor.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
        )
    ):
        return "INCORRECT_ATTEMPT"
    return None


def deterministic_wrong_tutor_result(
    tutor: TutorResult,
    wrong_attempt_count: int,
) -> TutorResult:
    if not is_support_failure(tutor):
        return tutor
    bounded_count = min(wrong_attempt_count, 4)
    strategy_by_count = {
        1: ("GUIDED_HINT", 1),
        2: ("GUIDED_HINT", 2),
        3: ("PROVIDE_VISUAL_CUE", None),
        4: ("SCAFFOLD", None),
    }
    strategy, hint_level = strategy_by_count[bounded_count]
    return tutor.model_copy(
        update={
            "response_strategy": strategy,
            "hint_level": hint_level,
        }
    )


def schema_interaction_request_id(
    session: SessionRecord,
    source_turn_id: str,
    event_type: str,
) -> str:
    return f"{session.session_id}:{source_turn_id}:{event_type}"


def catalog_error_code(session: SessionRecord, candidate: str | None) -> str | None:
    if candidate is None:
        return None
    for potential_error in schema_question(session).tutor_view.potential_errors:
        if potential_error.get("error_code") == candidate:
            return candidate
    return None


def db_error_code(session: SessionRecord, student_message: str) -> str | None:
    if session.student_model_event is None:
        return None
    normalized_message = normalize_exact_notation(student_message).casefold()
    selected_option = selected_option_submission(student_message)
    opt_id = selected_option[0].casefold() if selected_option is not None else None
    opt_text = (
        normalize_exact_notation(selected_option[1]).casefold()
        if selected_option is not None
        else None
    )

    for potential_error in schema_question(session).tutor_view.potential_errors:
        error_code = potential_error.get("error_code")
        response_patterns = potential_error.get("response_patterns")
        if not isinstance(error_code, str) or not isinstance(response_patterns, list):
            continue
        for pattern in response_patterns:
            if not isinstance(pattern, str):
                continue
            normalized_pattern = normalize_exact_notation(pattern).casefold()
            if (
                normalized_pattern == normalized_message
                or (
                    opt_id is not None
                    and (
                        normalized_pattern == opt_id
                        or normalized_pattern == f"option {opt_id}"
                    )
                )
                or (opt_text is not None and normalized_pattern == opt_text)
            ):
                return error_code
    return None


def validated_error_code(
    session: SessionRecord,
    student_message: str,
    tutor: TutorResult,
) -> str | None:
    if tutor.contribution is not None:
        if tutor.contribution.support_relevance != "MATCHED":
            return None
        return catalog_error_code(session, tutor.selected_error_code)
    return db_error_code(session, student_message)


def escalated_checkpoint(
    response: StudentModelSessionEventResponse,
) -> Phase3Checkpoint | None:
    """The checkpoint the escalation parked, keyed the way upstream keys it."""
    phase3 = response.journey_state.phase_3_independent_practice
    checkpoint = response.journey_state.return_checkpoint or phase3.return_checkpoint
    escalated = [
        skill
        for skill, state in phase3.repair_state_by_skill.items()
        if state.status == "PREREQUISITE_LOOKUP_REQUIRED"
    ]
    if checkpoint is not None and len(escalated) == 1 and escalated[0] != checkpoint.micro_skill_id:
        return checkpoint.model_copy(update={"micro_skill_id": escalated[0]})
    return checkpoint


async def resolve_prerequisite_route(
    session: SessionRecord,
    response: StudentModelSessionEventResponse,
    source_turn_id: str,
    student_model: StudentModelAdapter,
    access_token: str,
) -> StudentModelSessionEventResponse:
    """Answer the prerequisite lookup Student Model is waiting on (TC-29/30/31)."""
    checkpoint = escalated_checkpoint(response)
    if checkpoint is None:
        raise HTTPException(
            status_code=503,
            detail="Student Model escalated to a prerequisite lookup without a return checkpoint.",
        )
    route = await student_model.fetch_prerequisite_route(
        response.journey_state.topic_id,
        checkpoint.micro_skill_id,
        schema_interaction_request_id(
            session,
            source_turn_id,
            "PREREQUISITE_ROUTE_LOOKUP",
        ),
    )
    logger.info(
        "prerequisite_route_resolved",
        extra={
            "session_id": session.session_id,
            "topic_id": response.journey_state.topic_id,
            "micro_skill_id": checkpoint.micro_skill_id,
            "checkpoint_question_id": checkpoint.checkpoint_question_id,
            "prerequisite_micro_skill_count": len(route.prerequisite_micro_skills),
        },
    )
    return await student_model.send_session_event(
        PrerequisiteRouteResolvedEvent(
            request_id=schema_interaction_request_id(
                session,
                source_turn_id,
                "PREREQUISITE_ROUTE_RESOLVED",
            ),
            event_type="PREREQUISITE_ROUTE_RESOLVED",
            source_turn_id=source_turn_id,
            expected_journey_version=response.journey_state.version,
            topic_id=response.journey_state.topic_id,
            source_topic_id=response.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source_micro_skill_id=checkpoint.micro_skill_id,
            prerequisite_micro_skills=route.prerequisite_micro_skills,
        ),
        access_token,
    )


async def process_student_turn(
    context: AdapterContext,
    session: SessionRecord,
    access_token: str,
    student_model: StudentModelAdapter | None = None,
    tutor_engine: TutorEngineAdapter | None = None,
) -> StudentTurnResult:
    """Evaluate one student turn and apply its authoritative Schema 3.0 event."""
    adapters = get_adapters()
    sm = student_model or adapters.student_model
    te = tutor_engine or adapters.tutor

    require_learning_active(session)
    session = await initialize_restored_schema_phase(
        session,
        sm,
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

    student, tutor = await _invoke_tutor_pipeline(run_tutor_pipeline, context, sm, te)
    tutor = require_authored_canvas_confirmation(
        session,
        tutor,
        context.canvas_solution_complete_candidate,
    )
    if tutor.requires_written_math_evidence:
        return StudentTurnResult(student, tutor, None, None, session)
    if (
        context.has_canvas_evidence
        and tutor.mistake_classification is not None
        and tutor.mistake_classification.status == "no_mistake"
        and not context.canvas_solution_complete_candidate
    ):
        confirmation = "That step is correct. Keep going until you have the final answer."
        return StudentTurnResult(
            student,
            tutor.model_copy(
                update={
                    "evaluation": "PARTIALLY_CORRECT",
                    "response_strategy": "CONFIRM_CORRECT",
                    "tutor_message": confirmation,
                    "tutor_message_voice": confirmation,
                    "attempt_increment": 0,
                    "question_completed": False,
                    "answer_value_confirmed": False,
                    "recommended_conversation_action": "ACKNOWLEDGE_ANSWER",
                }
            ),
            None,
            None,
            session,
        )
    if (
        context.has_canvas_evidence
        and tutor.mistake_classification is not None
        and tutor.mistake_classification.status == "mistake_found"
        and tutor.intent != "SUBMITTING_ANSWER"
    ):
        return StudentTurnResult(
            student,
            tutor.model_copy(update={"attempt_increment": 0}),
            None,
            None,
            session,
        )
    scaffold_turn = session.current_scaffold_step_id is not None
    rules = load_classifier_rules()
    wrong_attempt_count = (
        session.wrong_attempt_count + 1
        if not scaffold_turn and is_support_failure(tutor)
        else session.wrong_attempt_count
    )
    if not scaffold_turn and tutor.contribution is None:
        tutor = deterministic_wrong_tutor_result(tutor, wrong_attempt_count)
    scaffold_step_satisfied = (
        scaffold_turn
        and session.scaffold_expected_response is not None
        and (
            tutor.evaluation == "CORRECT"
            if tutor.contribution is not None
            else scaffold_response_is_correct(
                context.message,
                session.scaffold_expected_response,
                tutor.evaluation,
                session.correct_answer or "",
                rules,
            )
        )
    )
    next_scaffold_failure_count = (
        session.scaffold_failure_count + 1
        if (
            scaffold_turn
            and not scaffold_step_satisfied
            and is_unresolved_scaffold_turn(tutor)
        )
        else session.scaffold_failure_count
    )
    atomic_guided_events_enabled = (
        get_settings().student_model_atomic_guided_events_enabled
    )
    scaffold_rescue_escalation = (
        atomic_guided_events_enabled
        and session.current_phase == "GUIDED_PRACTICE"
        and scaffold_turn
        and is_unresolved_scaffold_turn(tutor)
        and next_scaffold_failure_count
        >= rules.strategy_rules.scaffold_max_unresolved_turns
    )
    schema_managed = session.current_phase in {
        "GUIDED_PRACTICE",
        "INDEPENDENT_PRACTICE",
    } and (
        not scaffold_turn
        or tutor.scaffold_original_answer_correct
        or scaffold_rescue_escalation
    )
    event_type = guided_attempt_event_type(tutor, rules)
    response_is_wrong = is_support_failure(tutor)

    next_wrong_attempt_count = (
        session.wrong_attempt_count + 1
        if response_is_wrong
        else session.wrong_attempt_count
    )
    wrong_four_escalation = (
        atomic_guided_events_enabled
        and schema_managed
        and session.current_phase == "GUIDED_PRACTICE"
        and is_support_failure(tutor)
        and wrong_attempt_count >= 4
    )
    confusion_support_request = (
        schema_managed
        and session.current_phase == "GUIDED_PRACTICE"
        and tutor.intent == "EXPRESSING_CONFUSION"
        and tutor.guided_student_state == "STUCK"
    )
    support_escalation = (
        wrong_four_escalation
        or scaffold_rescue_escalation
        or confusion_support_request
    )
    if not schema_managed or (event_type is None and not support_escalation):
        return StudentTurnResult(student, tutor, None, None, session)

    micro_skill_ids = schema_event_micro_skills(session)
    highest_guided_support = (
        stored_event.journey_state.phase_2_guided_learning
        .highest_support_used_by_skill.get(micro_skill_ids[0], "NONE")
    )
    retry_skills = [
        skill for skill in micro_skill_ids
        if skill in (stored_event.journey_state.phase_3_independent_practice
                     .retry_required_micro_skill_ids)
    ]
    retry_required = bool(retry_skills)
    if support_escalation:
        next_stuck_count = session.stuck_count + 1
        escalation_type: Literal[
            "GUIDED_SUPPORT_REQUESTED",
            "GUIDED_SUPPORT_ESCALATION_REQUIRED",
            "GUIDED_STUCK_SUPPORT_REQUIRED",
            "MAXIMUM_GUIDED_SUPPORT_PARALLEL",
            "MAXIMUM_GUIDED_SUPPORT_REQUIRED",
        ]
        if scaffold_rescue_escalation and highest_guided_support == "PARALLEL_EXAMPLE":
            escalation_type = "MAXIMUM_GUIDED_SUPPORT_REQUIRED"
        elif scaffold_rescue_escalation and highest_guided_support == "SCAFFOLD":
            escalation_type = "MAXIMUM_GUIDED_SUPPORT_PARALLEL"
        elif confusion_support_request:
            escalation_type = (
                "GUIDED_STUCK_SUPPORT_REQUIRED"
                if next_stuck_count >= rules.strategy_rules.stuck_scaffold_min_count
                else "GUIDED_SUPPORT_REQUESTED"
            )
        elif highest_guided_support == "PARALLEL_EXAMPLE":
            escalation_type = "MAXIMUM_GUIDED_SUPPORT_REQUIRED"
        elif highest_guided_support == "SCAFFOLD":
            escalation_type = "MAXIMUM_GUIDED_SUPPORT_PARALLEL"
        else:
            escalation_type = "GUIDED_SUPPORT_ESCALATION_REQUIRED"
        logger.info(
            "guided_support_escalation_selected",
            extra={
                "question_id": session.question_id,
                "event_type": escalation_type,
                "detected_intent": tutor.intent,
                "next_stuck_count": next_stuck_count,
                "next_scaffold_failure_count": next_scaffold_failure_count,
                "highest_guided_support": highest_guided_support,
            },
        )
        escalation_error_code = validated_error_code(
            session,
            context.message,
            tutor,
        )
        escalation_event = GuidedSupportEvent(
            request_id=schema_interaction_request_id(
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
            triggering_response=(
                context.message
                if escalation_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
                and wrong_four_escalation
                and (escalation_error_code is not None or tutor.contribution is not None)
                else None
            ),
            error_code=escalation_error_code,
            unmapped_error_description=(
                tutor.contribution.error_description
                if tutor.contribution is not None and escalation_error_code is None
                else None
            ),
        )
        session = await store_pending_support_event(session, escalation_event)
        response = await sm.send_session_event(
            escalation_event,
            access_token,
        )
    elif session.current_phase == "INDEPENDENT_PRACTICE" and retry_required:
        response = await sm.send_session_event(
            IndependentRetryCompletedEvent(
                request_id=schema_interaction_request_id(
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
                micro_skill_ids=retry_skills + [
                    skill for skill in micro_skill_ids if skill not in retry_skills
                ],
                student_response=context.message,
                independent_success=event_type == "CORRECT_ATTEMPT",
                error_code=(
                    (
                        validated_error_code(session, context.message, tutor)
                    )
                    if event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
            ),
            access_token,
        )
    else:
        response = await sm.send_session_event(
            GuidedAttemptEvent(
                request_id=schema_interaction_request_id(
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
                    schema_support_used(session, micro_skill_ids)
                    if (
                        session.current_phase == "GUIDED_PRACTICE"
                        and event_type == "CORRECT_ATTEMPT"
                    )
                    else None
                ),
                error_code=(
                    (
                        validated_error_code(session, context.message, tutor)
                    )
                    if event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
                generated_support_text=(
                    tutor.contribution.generated_support_text
                    if tutor.contribution is not None
                    and tutor.contribution.support_relevance in {"UNMAPPED", "MISMATCHED"}
                    else None
                ),
                support_relevance=(
                    tutor.contribution.support_relevance
                    if tutor.contribution is not None and event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
                generated_visual_rows=(
                    tutor.contribution.generated_visual_rows
                    if tutor.contribution is not None and event_type == "INCORRECT_ATTEMPT"
                    and tutor.contribution.support_relevance in {"UNMAPPED", "MISMATCHED"}
                    else None
                ),
            ),
            access_token,
        )

    intervention = _authoritative_intervention(response)
    if intervention is not None and intervention.is_active:
        updated_session = await _apply_schema_event(session, response)
        return StudentTurnResult(student, tutor, response, response, updated_session)

    content_response = response
    rescue = guided_rescue(content_response)
    active_guided_rescue = presented_rescue(
        session,
        session.question_id,
        rescue,
        context.correct_answer,
        content_response.request_id,
        rules,
    )
    persisted_rescue_context = (
        rescue_context_for(active_guided_rescue)
        if active_guided_rescue is not None
        else None
    )
    tutor = tutor_with_guided_rescue(
        tutor,
        content_response,
        rules.guided_learning.canvas_rescue_presentation_enabled,
        context.correct_answer,
        rules.guided_learning.canvas_rescue_wording,
        persisted_rescue_context,
    )
    if persisted_rescue_context is not None:
        tutor = tutor.model_copy(
            update={
                "tutor_canvas_actions": plan_rescue_canvas_actions(
                    persisted_rescue_context,
                    context.source_turn_id,
                    context.correct_answer,
                    rules.guided_learning.canvas_rescue_wording,
                )
            }
        )
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
                escalation_type
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
        and not (
            active_guided_rescue is not None
            and active_guided_rescue.rescue_type == "TUTOR_SOLVED"
        )
        and (
            response.routing.next_action == "PROCEED_TO_PHASE_3"
            or (event_type == "CORRECT_ATTEMPT" and not guided.remaining_micro_skill_ids)
        )
    ):
        progressed = await complete_guided_progression(
            session, response, context.source_turn_id, access_token)
        response = progressed.student_model_event
        if response is None:
            raise RuntimeError("Guided progression lost its Student Model response.")
    prerequisite_repair_event: StudentModelSessionEventResponse | None = None
    if (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and not retry_required
        and not response.routing.content_gap_detected
        and response.status.status_code != "CONTENT_GAP"
        and event_type == "INCORRECT_ATTEMPT"
        and (
            response.phase_payload is None
            or response.phase_payload.question_set is None
            or not response.phase_payload.question_set.questions
        )
    ):
        phase3 = response.journey_state.phase_3_independent_practice
        target_skills = (
            phase3.retry_required_micro_skill_ids
            or phase3.unresolved_micro_skill_ids
            or micro_skill_ids
        )
        response = await sm.send_session_event(
            FreshIndependentQuestionRequestedEvent(
                request_id=schema_interaction_request_id(
                    session,
                    context.source_turn_id,
                    "FRESH_INDEPENDENT_QUESTION_REQUESTED",
                ),
                event_type="FRESH_INDEPENDENT_QUESTION_REQUESTED",
                source_turn_id=context.source_turn_id,
                expected_journey_version=response.journey_state.version,
                topic_id=response.journey_state.topic_id,
                student_id=session.student_id,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                target_micro_skill_ids=target_skills,
                used_question_ids=phase3.used_question_ids,
            ),
            access_token,
        )
    if (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and retry_required
        and not response.routing.content_gap_detected
        and response.phase_payload is None
        and response.journey_state.recommended_entry_phase
        == "PHASE_2_GUIDED_LEARNING"
    ):
        prerequisite_repair_event = response
        targets = response.journey_state.phase_2_guided_learning.target_micro_skill_ids
        if not targets:
            raise HTTPException(status_code=503, detail="Student Model omitted Guided repair targets.")
        response = await sm.send_session_event(
            GuidedQuestionSetRequestedEvent(
                request_id=schema_interaction_request_id(
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
                target_micro_skill_ids=targets,
            ),
            access_token,
        )
    if (
        response.routing.prerequisite_check_required
        and response.status.status_code == "PREREQUISITE_LOOKUP_REQUIRED"
    ):
        response = await resolve_prerequisite_route(
            session,
            response,
            context.source_turn_id,
            sm,
            access_token,
        )
    if active_guided_rescue is not None:
        session = session.model_copy(
            update={"active_guided_rescue": active_guided_rescue}
        )
    updated_session = await _apply_schema_event(session, response)
    if prerequisite_repair_event is not None:
        updated_session = await store_prerequisite_repair_event(
            updated_session,
            prerequisite_repair_event,
        )
    return StudentTurnResult(
        student,
        tutor,
        content_response,
        response,
        updated_session,
    )


# Alias for backward compatibility
process_answer_with_session_event = process_student_turn
