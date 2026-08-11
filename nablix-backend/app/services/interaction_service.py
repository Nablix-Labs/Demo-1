import hashlib
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from time import perf_counter
from typing import Final, Literal, cast
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.adapters.base import StudentModelAdapter
from app.adapters.provider import get_adapters
from app.ai_engine.classifier import (
    build_openai_ai_engine_client,
    contains_answer_reveal,
    detect_student_intent,
    generate_explain_again_response,
    guided_error_definitions,
    initial_guided_objective,
    normalize_exact_notation,
    resolve_guided_rubric,
)

from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.ai_engine.schemas import (
    ActiveScaffoldState,
    ExplainAgainRequest,
    RecordedMisconception,
    VisibleVisualCue as AIVisibleVisualCue,
)

from app.core.config import get_settings
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
    OCRTextRegion,
    SpatialMathToken,
    TutorAction,
    TutorResult,
    VisualCue,
    VisionOCRResult,
)
from app.models.fields import Phase
from app.models.guided_learning import (
    ActiveScaffold,
    EvaluationReasonCode,
    GuidedRescue,
    NudgeDelivery,
    ScaffoldEvaluationContext,
    WrongEscalationCode,
)

from app.models.interaction import (
    InteractionRequest,
    InteractionResponse,
    StaleTurnResponse,
)
from app.models.session import (
    QuestionAttemptRecord,
    NudgeDeliveryRecord,
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
    QuestionType,
    StudentModelSessionEventResponse,
    StudentModelQuestion,
    SupportUsed,
)
from app.services.guided_question_opening import guided_question_opening
from app.services.canvas_annotations import assign_step_ids, plan_canvas_draw
from app.services.canvas_spatial import (
    align_step_tokens,
    associate_strokes_with_steps,
    parse_mathml_tokens,
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
    inactivity_policy,
    interaction_payload_fingerprint_for,
    last_interaction_response_for,
    nudge_deliveries_for_tutor_turn,
    nudge_delivery_for,
    store_nudge_delivery,
    update_nudge_delivery_status,
    update_side_channel_state,
    update_interaction_state,
)
from app.services.student_model_session import (
    PHASE_FROM_STUDENT_MODEL,
)
from app.services.snapshot_store import build_reference, store_snapshot


_NUMBER_WORD_VALUES: Final[dict[str, str]] = {
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
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
}


@dataclass(frozen=True)
class Phase3TerminalAttempt:
    question_id: str
    outcome: Literal["CORRECT", "INCORRECT"]
    selected_error_code: str | None


_SCAFFOLD_INTEGER_TOKEN: Final[str] = (
    r"-?\d+|" + "|".join(_NUMBER_WORD_VALUES)
)
_ADDITION_CHANGE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"(?:\+|(?<!\w)(?:plus|add(?:s|ed|ing)?(?:\s+by)?|"
    rf"increase(?:s|d|ing)?(?:\s+by)?))\s*"
    rf"(?P<operand>{_SCAFFOLD_INTEGER_TOKEN})(?!\w)",
    re.IGNORECASE,
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
_INACTIVITY_MESSAGE = "Are you still with me? Take your time and continue when you're ready."
_EXPLICIT_HELP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:give|show|offer)\s+me\s+(?:a\s+)?hint\b|"
    r"\b(?:can|could|may)\s+i\s+(?:have|get)\s+(?:a\s+)?hint\b|"
    r"\bi\s+(?:need|want)\s+(?:a\s+)?hint\b|"
    r"\bhelp\s+me\b|\bi\s+need\s+help\b",
    re.IGNORECASE,
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
class _CanvasEvidence:
    submission_id: str
    snapshot_reference: str
    ocr: VisionOCRResult
    spatial_tokens: list[SpatialMathToken]
    ocr_latency_ms: float


def _normalised_mathml_tokens(mathml: str) -> str:
    return "".join(token.text for token in parse_mathml_tokens(mathml)).replace(" ", "")


def _with_confirmed_mathml_regions(ocr: VisionOCRResult) -> VisionOCRResult:
    """Attach MathML only when Mathpix returned one unambiguous block per line."""

    if len(ocr.mathml_blocks) != len(ocr.detected_regions):
        return ocr
    regions: list[OCRTextRegion] = []
    for region, mathml in zip(ocr.detected_regions, ocr.mathml_blocks):
        if _normalised_mathml_tokens(mathml) != region.text.replace(" ", ""):
            return ocr
        regions.append(region.model_copy(update={"mathml": mathml}))
    return ocr.model_copy(update={"detected_regions": regions})


def _is_complete_correct_canvas(
    ocr: VisionOCRResult | None,
    correct_answer: str | None,
) -> bool:
    return (
        ocr is not None
        and not ocr.needs_clarification
        and ocr.final_answer is not None
        and normalize_exact_notation(ocr.final_answer)
        == normalize_exact_notation(correct_answer or "")
    )


async def _canvas_evidence_for(request: InteractionRequest) -> _CanvasEvidence | None:
    canvas_state = request.canvas_state
    if canvas_state is None:
        return None
    settings = get_settings()
    if len(canvas_state.snapshot_data_url) > settings.max_snapshot_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Canvas snapshot exceeds the {settings.max_snapshot_bytes} byte limit.",
        )
    if request.turn_id is None:
        raise RuntimeError("validated interaction is missing turn_id")

    snapshot_reference = build_reference(request.turn_id)
    store_snapshot(snapshot_reference, canvas_state.snapshot_data_url)
    started = perf_counter()
    ocr = await get_adapters().vision.recognize(canvas_state.snapshot_data_url)
    ocr = ocr.model_copy(update={"detected_regions": assign_step_ids(ocr.detected_regions)})
    ocr = _with_confirmed_mathml_regions(ocr)
    strokes_by_step = associate_strokes_with_steps(canvas_state.strokes, ocr.detected_regions)
    spatial_tokens: list[SpatialMathToken] = []
    for region in ocr.detected_regions:
        if region.step_id is None or region.mathml is None:
            continue
        spatial_tokens.extend(
            align_step_tokens(
                region.step_id,
                region.mathml,
                region.text,
                strokes_by_step.get(region.step_id, []),
                region,
            )
        )
    return _CanvasEvidence(
        submission_id=request.turn_id,
        snapshot_reference=snapshot_reference,
        ocr=ocr,
        spatial_tokens=spatial_tokens,
        ocr_latency_ms=(perf_counter() - started) * 1000,
    )


def _is_wrong_evaluation(tutor: TutorResult) -> bool:
    return (
        tutor.guided_student_state == "WRONG"
        or (
            tutor.evaluation == "INCORRECT"
            and tutor.intent != "EXPRESSING_CONFUSION"
        )
    )


def _is_support_failure(tutor: TutorResult) -> bool:
    """Return whether an unresolved answer should advance guided support."""
    return _is_wrong_evaluation(tutor)


def _guided_attempt_event_type(
    tutor: TutorResult,
    rules: ClassifierRulesConfig,
) -> Literal["CORRECT_ATTEMPT", "INCORRECT_ATTEMPT"] | None:
    """Map every answer that advances support to an authoritative attempt event."""
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
        or _is_support_failure(tutor)
        or (
            tutor.guided_student_state is None
            and configured_event is None
            and tutor.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
        )
    ):
        return "INCORRECT_ATTEMPT"
    return None


def _guided_rescue(
    event: StudentModelSessionEventResponse | None,
) -> GuidedRescue | None:
    if event is None or event.phase_payload is None:
        return None
    payload = event.phase_payload
    if payload.payload_type != "RESCUE" or payload.rescue_to_serve is None:
        return None
    rescue = payload.rescue_to_serve
    try:
        return GuidedRescue.model_validate(
            {
                **rescue,
                "parallel_example": rescue.get("parallel_example"),
                "tutor_solved": rescue.get("tutor_solved"),
            }
        )
    except ValidationError as error:
        raise RuntimeError(
            "Student Model returned malformed guided rescue content "
            f"for question_id={event.journey_state.phase_2_guided_learning.current_question_id}: "
            f"{error}"
        ) from error


def _guided_rescue_message(rescue: GuidedRescue) -> str | None:
    if rescue.rescue_type == "PARALLEL_EXAMPLE":
        example = rescue.parallel_example
        if example is None:
            return None
        worked_steps = " ".join(example.worked_steps)
        return (
            f"Let’s work through a similar example. {example.problem} "
            f"{worked_steps} The result is {example.final_answer}. "
            "Now try the original question again."
        )
    solved = rescue.tutor_solved
    if solved is None:
        return None
    answer_steps = " ".join(solved.answer_steps)
    return " ".join(
        part
        for part in [
            "Let’s solve this one together.",
            solved.explanation,
            answer_steps,
        ]
        if part
    )


def _tutor_with_guided_rescue(
    tutor: TutorResult,
    event: StudentModelSessionEventResponse,
) -> TutorResult:
    rescue = _guided_rescue(event)
    if rescue is None:
        return tutor
    message = _guided_rescue_message(rescue)
    if message is None:
        logger.warning(
            "guided_rescue_content_missing",
            extra={
                "request_id": event.request_id,
                "rescue_type": rescue.rescue_type,
            },
        )
        return tutor
    parallel = rescue.rescue_type == "PARALLEL_EXAMPLE"
    return tutor.model_copy(
        update={
            "response_strategy": (
                "PROVIDE_WORKED_EXAMPLE" if parallel else "TUTOR_SOLVED"
            ),
            "tutor_message": message,
            "tutor_message_voice": message,
            "voice_optimised": True,
            "answer_reveal_allowed": not parallel,
            "recommended_conversation_action": (
                "ASK_QUESTION" if parallel else "WAIT_FOR_STUDENT"
            ),
            "question_completed": not parallel,
        }
    )


def _evaluation_reason(tutor: TutorResult) -> EvaluationReasonCode:
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
    if (
        context.has_canvas_evidence
        and tutor.mistake_classification is not None
        and tutor.mistake_classification.status == "no_mistake"
        and not context.canvas_solution_complete_candidate
    ):
        confirmation = "That step is correct. Keep going until you have the final answer."
        return (
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
        return student, tutor.model_copy(update={"attempt_increment": 0}), None, None, session
    scaffold_turn = session.current_scaffold_step_id is not None
    wrong_attempt_count = (
        session.wrong_attempt_count + 1
        if not scaffold_turn and _is_support_failure(tutor)
        else session.wrong_attempt_count
    )
    if not scaffold_turn:
        tutor = _deterministic_wrong_tutor_result(tutor, wrong_attempt_count)
    rules = load_classifier_rules()
    schema_managed = session.current_phase in {
        "GUIDED_PRACTICE",
        "INDEPENDENT_PRACTICE",
    } and (not scaffold_turn or tutor.scaffold_original_answer_correct)
    event_type = _guided_attempt_event_type(tutor, rules)
    response_is_wrong = _is_support_failure(tutor)

    next_wrong_attempt_count = (
        session.wrong_attempt_count + 1
        if response_is_wrong
        else session.wrong_attempt_count
    )
    atomic_guided_events_enabled = (
        get_settings().student_model_atomic_guided_events_enabled
    )
    wrong_four_escalation = (
        atomic_guided_events_enabled
        and schema_managed
        and session.current_phase == "GUIDED_PRACTICE"
        and _is_support_failure(tutor)
        and wrong_attempt_count >= 4
    )
    stuck_escalation = (
        schema_managed
        and session.current_phase == "GUIDED_PRACTICE"
        and tutor.intent == "EXPRESSING_CONFUSION"
        and (
            tutor.response_strategy in {"SCAFFOLD", "PROVIDE_WORKED_EXAMPLE"}
            or session.stuck_count + 1
            >= rules.strategy_rules.stuck_scaffold_min_count
        )
    )
    support_escalation = wrong_four_escalation or stuck_escalation
    if not schema_managed or (event_type is None and not support_escalation):
        return student, tutor, None, None, session

    micro_skill_ids = _schema_event_micro_skills(session)
    highest_guided_support = (
        stored_event.journey_state.phase_2_guided_learning
        .highest_support_used_by_skill.get(micro_skill_ids[0], "NONE")
    )
    retry_required = bool(
        stored_event.journey_state.phase_3_independent_practice
        .retry_required_micro_skill_ids
    )
    if support_escalation:
        escalation_type: Literal[
            "GUIDED_SUPPORT_ESCALATION_REQUIRED",
            "GUIDED_STUCK_SUPPORT_REQUIRED",
            "MAXIMUM_GUIDED_SUPPORT_PARALLEL",
            "MAXIMUM_GUIDED_SUPPORT_REQUIRED",
        ] = (
            "MAXIMUM_GUIDED_SUPPORT_REQUIRED"
            if highest_guided_support == "PARALLEL_EXAMPLE"
            else "MAXIMUM_GUIDED_SUPPORT_PARALLEL"
            if highest_guided_support == "SCAFFOLD"
            else "GUIDED_STUCK_SUPPORT_REQUIRED"
            if stuck_escalation and not wrong_four_escalation
            else "GUIDED_SUPPORT_ESCALATION_REQUIRED"
        )
        escalation_error_code = _validated_error_code(
            session,
            context.message,
            tutor,
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
                triggering_response=(
                    context.message
                    if escalation_type == "GUIDED_SUPPORT_ESCALATION_REQUIRED"
                    and wrong_four_escalation
                    else None
                ),
                error_code=escalation_error_code,
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
                        _validated_error_code(session, context.message, tutor)
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
                        _validated_error_code(session, context.message, tutor)
                    )
                    if event_type == "INCORRECT_ATTEMPT"
                    else None
                ),
            ),
            access_token,
        )

    content_response = response
    tutor = _tutor_with_guided_rescue(tutor, content_response)
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


_EXPLICIT_ASSIGNMENT = re.compile(
    r"\b([A-Za-z])\s*=\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\b"
)
_SPOKEN_NUMERIC_ANSWER = re.compile(
    r"\b(?:got|answer\s*(?:=|is)?|solution\s*(?:=|is)?)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+))\b",
    flags=re.IGNORECASE,
)


def _spoken_answer_conflicts_with_canvas(
    student_message: str,
    canvas_final_answer: str | None,
) -> bool:
    """Detect a plainly stated numeric answer that disagrees with the board."""

    if canvas_final_answer is None:
        return False
    normalized_message = _normalize_voice_transcript(student_message)
    spoken = _EXPLICIT_ASSIGNMENT.search(normalized_message)
    board = _EXPLICIT_ASSIGNMENT.search(canvas_final_answer)
    if board is None:
        return False
    if spoken is not None:
        return (
            spoken.group(1).lower() == board.group(1).lower()
            and spoken.group(2) != board.group(2)
        )
    numeric_answer = _SPOKEN_NUMERIC_ANSWER.search(normalized_message)
    return numeric_answer is not None and numeric_answer.group(1) != board.group(2)


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


def require_phase3_submission(
    session: SessionRecord,
    submission_confirmed: bool | None,
    submission_kind: Literal["CANVAS", "CHOICE"] | None,
    selected_option_id: str | None,
) -> None:
    """Validate an explicit Phase 3 submission against its active question."""

    if submission_confirmed is not True:
        raise HTTPException(
            status_code=409,
            detail="Independent Practice answers require explicit submission confirmation.",
        )
    if submission_kind == "CANVAS":
        return
    if submission_kind != "CHOICE":
        raise HTTPException(
            status_code=409,
            detail="Independent Practice answers must use Canvas or Choice.",
        )
    option_ids = {
        option.option_id
        for option in _schema_question(session).student_view.options
    }
    if selected_option_id not in option_ids:
        raise HTTPException(
            status_code=409,
            detail="The selected option is not part of the active Independent Practice question.",
        )


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


def _catalog_error_code(session: SessionRecord, candidate: str | None) -> str | None:
    if candidate is None:
        return None
    for potential_error in _schema_question(session).tutor_view.potential_errors:
        if potential_error.get("error_code") == candidate:
            return candidate
    return None


def _validated_error_code(
    session: SessionRecord,
    student_message: str,
    tutor: TutorResult,
) -> str | None:
    return (
        _db_error_code(session, student_message)
        or _catalog_error_code(session, tutor.selected_error_code)
        or _catalog_error_code(session, tutor.error_type)
    )


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
            if not missing_question:
                return session
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
            if not missing_question:
                return session
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
        cue_type = item.get("cue_type", item.get("visual_cue_type"))
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
            cue_id=content_id,
            cue_type=cue_type if isinstance(cue_type, str) else None,
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
    canonical_answer: str,
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
    if _matches_authored_scaffold_concept(
        normalized_student,
        normalized_expected,
        _normalize_scaffold_response(canonical_answer),
    ):
        return True
    expected_addition = _addition_change_operand(expected_response)
    student_addition = _addition_change_operand(student_message)
    if expected_addition is not None and student_addition == expected_addition:
        return True
    return tutor_evaluation == "CORRECT"


def _matches_authored_scaffold_concept(
    student: str,
    expected: str,
    canonical_answer: str,
) -> bool:
    """Accept concise semantic replies grounded in the authored answer."""
    alternatives = {
        alternative.strip()
        for alternative in re.split(r"\bor\b|\|", expected)
        if alternative.strip()
    }
    if any(_contains_scaffold_response(student, value) for value in alternatives):
        return True

    quantity_words = {"number", "quantity", "value", "variable"}
    student_words = set(student.split())
    expected_words = set(expected.split())
    if (
        student_words & quantity_words
        and expected_words & quantity_words
        and student_words & {"starting", "changing"}
        and expected_words & {"starting", "changing"}
    ):
        return True

    student_symbols = set(re.findall(r"(?<!\w)[a-z](?!\w)", student))
    authored_symbols = set(
        re.findall(
            r"(?<!\w)[a-z](?!\w)",
            canonical_answer,
        )
    )
    expects_changing_quantity = bool(
        expected_words & quantity_words
        or expected_words & {"starting", "changing"}
    )
    return bool(
        expects_changing_quantity
        and student_symbols
        and student_symbols <= authored_symbols
    )


def _addition_change_operand(value: str) -> str | None:
    match = _ADDITION_CHANGE_PATTERN.search(value.casefold().replace("＋", "+"))
    if match is None:
        return None
    operand = match.group("operand").casefold()
    if operand in _NUMBER_WORD_VALUES:
        return _NUMBER_WORD_VALUES[operand]
    return str(int(operand))


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


def _deterministic_wrong_tutor_result(
    tutor: TutorResult,
    wrong_attempt_count: int,
) -> TutorResult:
    if not _is_support_failure(tutor):
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


def _independent_correct_in_session(session: SessionRecord) -> int:
    # Unaided corrects in any phase — the same semantics as the classifier's
    # independent_success flag, which Saravanan's promotion gate counts.
    return sum(
        attempt.evaluation == "CORRECT" and attempt.hint_level_used == 0
        for attempt in session.per_question_history
    )


def _next_hint_count_from(session: SessionRecord) -> int:
    event = session.student_model_event
    if event is None:
        return session.hint_count
    guided = event.journey_state.phase_2_guided_learning
    current_hint_count = getattr(guided, "current_hint_count", None)
    return (
        current_hint_count
        if isinstance(current_hint_count, int) and current_hint_count >= 0
        else session.hint_count
    )


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
            "last_tutor_response_at": datetime.now(timezone.utc),
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


def _may_force_complete_repeated_explanation(
    current_phase: Phase,
    answer_value_confirmed: bool,
    explanation_request_count: int,
) -> bool:
    """Allow the legacy loop-breaker only outside evidence-driven guidance."""

    return (
        current_phase != "GUIDED_PRACTICE"
        and answer_value_confirmed
        and explanation_request_count >= 2
    )


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
    if request.turn_id is None:
        return None
    response = last_interaction_response_for(session.session_id, request.turn_id)
    if response is None and request.turn_id != session.last_processed_turn_id:
        return None
    if response is None:
        raise RuntimeError(
            f"cached response is missing for duplicate session_id={session.session_id} "
            f"turn_id={request.turn_id}"
        )
    fingerprint = interaction_payload_fingerprint_for(session.session_id, request.turn_id)
    if fingerprint is not None and fingerprint != _request_fingerprint(request):
        raise HTTPException(
            status_code=409,
            detail="turn_id was already accepted with different transcript or canvas evidence.",
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


def _guided_support_levels(session: SessionRecord) -> tuple[SupportUsed, SupportUsed]:
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
    active_support_level: SupportUsed = (
        support_type
        if support_type in _SUPPORT_RANK
        else "VISUAL_CUE"
        if support_type == "HINT_AND_VISUAL_CUE"
        else "NONE"
    )
    highest_support_used: SupportUsed = (
        max(
            guided.highest_support_used_by_skill.values(),
            key=_SUPPORT_RANK.index,
            default="NONE",
        )
        if guided is not None
        else "NONE"
    )
    return active_support_level, highest_support_used


def _response_from(
    session_id: str,
    student_id: str,
    turn_id: str,
    interaction_type: str,
    nudge_id: str | None,
    session: SessionRecord,
    message: str,
    message_voice: str,
    visual_cue: VisualCue | None,
    scaffold_steps: list[str],
    session_summary: SessionSummary | None,
    conversation_action: ConversationAction,
    attempt_increment: int,
    status: Literal["CLARIFICATION_REQUIRED", "NUDGE_SUPPRESSED", "processed"] | None,
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
    nudge_delivery = (
        nudge_delivery_for(session.session_id, nudge_id or turn_id)
        if interaction_type in {"INACTIVITY_NUDGE", "NUDGE_PRESENTED"}
        else None
    )
    phase3_attempt = _phase3_terminal_attempt(stored_event)
    phase3_silent = (
        session.current_phase == "INDEPENDENT_PRACTICE"
        and previous_phase != "GUIDED_PRACTICE"
    )
    if phase3_silent and phase3_attempt is not None:
        outcome = phase3_attempt.outcome
        message = (
            "Answer recorded."
            if outcome == "CORRECT"
            else "We'll review this one before a fresh independent check."
        )
        message_voice = ""
        visual_cue = None
        scaffold_steps = []
    return InteractionResponse(
        session_id=session_id,
        student_id=student_id,
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
        show_hint_button=False if phase3_silent else session.show_hint_button,
        show_visual_cue=False if phase3_silent else session.show_visual_cue,
        visual_cue=visual_cue,
        show_scaffold_panel=False if phase3_silent else session.show_scaffold_panel,
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
        student_model_event=None if phase3_silent else session.student_model_event,
        student_model_state=None if phase3_silent else session.student_model_state,
        active_teaching_objective=None if phase3_silent else active_objective,
        first_unresolved_concept_id=(
            None
            if phase3_silent
            else
            active_objective.missing_concept_ids[0]
            if active_objective is not None
            and active_objective.missing_concept_ids
            else None
        ),
        active_support_level="NONE" if phase3_silent else active_support_level,
        highest_support_used="NONE" if phase3_silent else highest_support_used,
        consecutive_stuck_count=session.stuck_count,
        wrong_attempt_count=session.wrong_attempt_count,
        intervention_triggered=session.wrong_attempt_count >= 4,
        routing_reason_code=(
            None
            if phase3_silent
            else
            stored_event.routing.reason_code if stored_event is not None else None
        ),
        active_scaffold=None if phase3_silent else _active_scaffold(session),
        inactivity_policy=inactivity_policy(),
        nudge_delivery=nudge_delivery,
        phase3_submission_confirmed=phase3_attempt is not None if phase3_silent else None,
        independent_outcome=(phase3_attempt.outcome if phase3_attempt else None),
        independent_success=(
            phase3_attempt.outcome == "CORRECT" if phase3_attempt else None
        ),
        independent_attempt_terminal=phase3_attempt is not None if phase3_silent else None,
        phase3_locked_question_id=(
            phase3_attempt.question_id if phase3_attempt else None
        ),
        selected_error_code=(
            None if phase3_silent else session.selected_error_code
        ),
        first_error_step=None,
    )


def _phase3_terminal_attempt(
    stored_event: StudentModelSessionEventResponse | None,
) -> Phase3TerminalAttempt | None:
    if stored_event is None or not isinstance(stored_event.event_result, dict):
        return None
    attempt = stored_event.event_result.get("attempt")
    if not isinstance(attempt, dict):
        return None
    question_id = attempt.get("question_id")
    outcome = attempt.get("evaluation")
    if not isinstance(question_id, str) or outcome not in {"CORRECT", "INCORRECT"}:
        return None
    detected_errors = stored_event.event_result.get("detected_errors")
    first_error = (
        detected_errors[0]
        if isinstance(detected_errors, list) and detected_errors
        else None
    )
    selected_error_code = (
        first_error.get("error_code")
        if isinstance(first_error, dict) and isinstance(first_error.get("error_code"), str)
        else None
    )
    return Phase3TerminalAttempt(question_id, outcome, selected_error_code)


def _cache_response(
    request: InteractionRequest,
    response: InteractionResponse,
) -> InteractionResponse:
    if request.turn_id is None:
        raise RuntimeError("validated interaction is missing turn_id")
    cache_interaction_response(
        request.session_id,
        request.turn_id,
        response,
        _request_fingerprint(request),
    )
    return response


def _request_fingerprint(request: InteractionRequest) -> str:
    payload = request.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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


def _is_explicit_help_request(request: InteractionRequest) -> bool:
    """Recognise an explicit request for support before answer evaluation."""
    if request.interaction_type != "ANSWER_SUBMISSION":
        return False
    message = request.text_input or request.voice_transcript or ""
    return _EXPLICIT_HELP_PATTERN.search(message) is not None


def _support_presentation(
    event: StudentModelSessionEventResponse,
) -> tuple[
    str | None,
    VisualCue | None,
    list[str],
    ConversationAction | None,
    SupportUsed | None,
]:
    """Validate and unpack exactly one Student Model support rung."""
    payload = event.phase_payload
    support = payload.support_to_serve if payload is not None else None
    if support is None:
        raise RuntimeError(
            "Student Model returned no support_to_serve for a guided support request."
        )
    support_type = support.get("support_type")
    hint = _schema_hint(event)
    visual_cue = _schema_visual_cue(event)
    scaffold_steps = _schema_support_steps(event)
    if support_type == "HINT":
        if hint is None:
            logger.warning(
                "guided_support_content_missing",
                extra={
                    "request_id": event.request_id,
                    "support_type": support_type,
                    "missing_content": "hint",
                },
            )
            return None, None, [], None, None
        return hint, None, [], "GIVE_HINT", "HINT"
    if support_type in {"VISUAL_CUE", "HINT_AND_VISUAL_CUE"}:
        if visual_cue is None:
            logger.warning(
                "guided_support_content_missing",
                extra={
                    "request_id": event.request_id,
                    "support_type": support_type,
                    "missing_content": "visual_cue",
                },
            )
            if hint is not None:
                return hint, None, [], "GIVE_HINT", "HINT"
            return None, None, [], None, None
        message = hint or visual_cue.description
        if not message:
            raise RuntimeError(
                f"Student Model returned {support_type} without student-facing guidance."
            )
        return message, visual_cue, [], "GIVE_HINT", "VISUAL_CUE"
    if support_type == "SCAFFOLD":
        scaffold_state = _schema_scaffold_state(event)
        if (
            not scaffold_steps
            or scaffold_state.get("scaffold_id") is None
            or scaffold_state.get("current_scaffold_step_id") is None
            or scaffold_state.get("scaffold_expected_response") is None
        ):
            logger.warning(
                "guided_support_content_missing",
                extra={
                    "request_id": event.request_id,
                    "support_type": support_type,
                    "missing_content": "scaffold",
                },
            )
            if hint is not None:
                return hint, None, [], "GIVE_HINT", "HINT"
            return None, None, [], None, None
        return scaffold_steps[0], None, scaffold_steps, "ASK_QUESTION", "SCAFFOLD"
    raise RuntimeError(
        f"Student Model returned unsupported guided support_type={support_type!r}."
    )


async def _guided_help_response(
    request: InteractionRequest,
    session: SessionRecord,
    access_token: str,
) -> InteractionResponse:
    if session.current_phase != "GUIDED_PRACTICE":
        raise HTTPException(
            status_code=409,
            detail="HELP_REQUEST is available only during Guided Practice.",
        )
    if session.student_model_event is None or session.question_id is None:
        raise HTTPException(
            status_code=409,
            detail="HELP_REQUEST requires an active Student Model question.",
        )
    micro_skill_ids = _schema_event_micro_skills(session)
    stored_event = session.student_model_event
    event = await get_adapters().student_model.send_session_event(
        GuidedSupportEvent(
            request_id=_schema_interaction_request_id(
                session,
                request.turn_id,
                "GUIDED_SUPPORT_REQUESTED",
            ),
            event_type="GUIDED_SUPPORT_REQUESTED",
            source_turn_id=request.turn_id,
            expected_journey_version=stored_event.journey_state.version,
            topic_id=stored_event.journey_state.topic_id,
            student_id=session.student_id,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            question_id=session.question_id,
            micro_skill_id=micro_skill_ids[0],
        ),
        access_token,
    )
    message, visual_cue, scaffold_steps, conversation_action, support_level = (
        _support_presentation(event)
    )
    rules = load_classifier_rules()
    for scaffold_prompt in scaffold_steps:
        _validate_scaffold_prompt(
            scaffold_prompt,
            session.correct_answer,
            rules,
        )
    event_session = _apply_schema_event(session, event)
    history = _updated_conversation_history(
        session.conversation_history,
        request.text_input or request.voice_transcript or "Help requested.",
        message,
        rules.conversation_rules.max_recent_messages,
    )
    last_action, expected_response = _conversation_state_for(
        conversation_action,
        False,
        None,
    )
    updated_session = update_interaction_state(
        request.session_id,
        request.student_id,
        event_session,
        event_session.current_phase,
        _next_hint_count_from(event_session),
        event_session.current_phase,
        request.transcript_confidence,
        request.canvas_snapshot_id,
        None,
        visual_cue is not None,
        bool(scaffold_steps),
        scaffold_steps,
        {
            "interaction_state_version": session.interaction_state_version + 1,
            "conversation_history": history,
            **_schema_scaffold_state(event),
            **_turn_updates(request, last_action, expected_response),
        },
    )
    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=request.turn_id,
        interaction_type="HELP_REQUEST",
        nudge_id=None,
        session=updated_session,
        message=message,
        message_voice=message,
        visual_cue=visual_cue,
        scaffold_steps=scaffold_steps,
        session_summary=None,
        conversation_action=conversation_action,
        attempt_increment=0,
        status=None,
        retry_safe=True,
    ).model_copy(
        update={
            "support_served_this_turn": support_level,
            "active_support_level": support_level,
            "routing_reason_code": event.routing.reason_code,
        }
    )
    return _cache_response(request, response)


def _active_scaffold(session: SessionRecord) -> ActiveScaffold | None:
    if (
        session.scaffold_id is None
        or session.current_scaffold_step_id is None
        or session.scaffold_step_number <= 0
        or session.scaffold_total_steps <= 0
        or not session.scaffold_steps
    ):
        return None
    return ActiveScaffold(
        scaffold_id=session.scaffold_id,
        current_step_id=session.current_scaffold_step_id,
        step_number=session.scaffold_step_number,
        total_steps=session.scaffold_total_steps,
        step_text=session.scaffold_steps[0],
        step_voice=None,
    )


def _claim_inactivity_nudge(
    request: InteractionRequest,
    session: SessionRecord,
) -> NudgeDeliveryRecord | None:
    policy = inactivity_policy()
    source_turn_id = request.previous_tutor_turn_id
    if source_turn_id is None or session.question_id is None:
        raise HTTPException(status_code=409, detail="No active tutor turn to nudge.")
    if session.expected_student_response == "NONE":
        return None
    now = datetime.now(timezone.utc)
    idle_since = session.last_tutor_response_at or session.started_at
    server_idle_ms = int((now - idle_since).total_seconds() * 1000)
    if (
        server_idle_ms < policy.initial_idle_threshold_ms
    ):
        return None
    deliveries = nudge_deliveries_for_tutor_turn(session.session_id, source_turn_id)
    if len(deliveries) >= policy.generated_nudge_rate_limit:
        return None
    presented = [item for item in deliveries if item.status == "PRESENTED"]
    if len(presented) >= policy.max_nudges_per_tutor_turn:
        return None
    if deliveries:
        elapsed_ms = int((now - deliveries[-1].created_at).total_seconds() * 1000)
        if elapsed_ms < policy.cooldown_ms:
            return None
    return store_nudge_delivery(
        NudgeDeliveryRecord(
            interaction_id=request.turn_id,
            session_id=session.session_id,
            source_tutor_turn_id=source_turn_id,
            question_id=session.question_id,
            message=_INACTIVITY_MESSAGE,
            message_voice=_INACTIVITY_MESSAGE,
            status="GENERATED",
            created_at=now,
        )
    )


def _acknowledge_inactivity_nudge(
    request: InteractionRequest,
    session: SessionRecord,
) -> NudgeDeliveryRecord:
    if request.nudge_id is None:
        raise HTTPException(status_code=422, detail="nudge_id is required.")
    record = nudge_delivery_for(session.session_id, request.nudge_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Nudge delivery was not found.")
    if record.source_tutor_turn_id != request.previous_tutor_turn_id:
        raise HTTPException(status_code=409, detail="Nudge belongs to an older tutor turn.")
    if record.status == "PRESENTED":
        return record
    if record.status != "GENERATED":
        raise HTTPException(
            status_code=409,
            detail=f"Nudge cannot be presented from status {record.status}.",
        )
    now = datetime.now(timezone.utc)
    return update_nudge_delivery_status(
        session.session_id,
        record.interaction_id,
        "PRESENTED",
        now,
        now,
    )


def _tutor_side_channel_updates(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
) -> dict[str, object]:
    return {
        "last_processed_turn_id": request.turn_id,
        "last_tutor_turn_id": _new_tutor_turn_id(),
        "last_tutor_response_at": datetime.now(timezone.utc),
        "conversation_history": [
            *session.conversation_history,
            ConversationMessage(role="assistant", content=message),
        ],
    }


def _nudge_side_channel_updates(
    request: InteractionRequest,
    session: SessionRecord,
    message: str | None,
) -> dict[str, object]:
    if request.previous_tutor_turn_id is None:
        raise RuntimeError("validated inactivity request is missing its tutor turn")
    deliveries = nudge_deliveries_for_tutor_turn(
        session.session_id,
        request.previous_tutor_turn_id,
    )
    updates: dict[str, object] = {
        "last_processed_turn_id": request.turn_id,
        "nudge_generated_count": len(deliveries),
        "nudge_presented_count": sum(
            item.status == "PRESENTED" for item in deliveries
        ),
    }
    if message is not None:
        updates["conversation_history"] = [
            *session.conversation_history,
            ConversationMessage(role="assistant", content=message),
        ]
    return updates


def _side_channel_response(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
    message_voice: str,
    conversation_action: ConversationAction,
    state_updates: dict[str, object],
) -> InteractionResponse:
    updated_session = update_side_channel_state(session, state_updates)
    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=request.turn_id or "TURN-0000",
        interaction_type=request.interaction_type,
        nudge_id=request.nudge_id,
        session=updated_session,
        message=message,
        message_voice=message_voice,
        visual_cue=None,
        scaffold_steps=updated_session.scaffold_steps,
        session_summary=None,
        conversation_action=conversation_action,
        attempt_increment=0,
        status=None,
        retry_safe=True,
    )
    return _cache_response(request, response)



def _contextual_nudge_message(session: SessionRecord) -> str:
    if session.current_scaffold_step_id is not None and session.scaffold_steps:
        return (
            "I'm still here with you. Look at the current step: "
            f"{session.scaffold_steps[0]} What would you try?"
        )
    if session.current_question is not None:
        return (
            "I'm still here with you. Looking at the question, what is the first "
            "thing you would try?"
        )
    return "I'm still here with you. Tell me what you are thinking so far."


def _nudge_eligible(session: SessionRecord, now: datetime) -> bool:
    policy = inactivity_policy()
    elapsed_ms = int((now - session.last_tutor_response_at).total_seconds() * 1000)
    if session.expected_student_response == "NONE":
        return False
    if elapsed_ms < policy.initial_idle_threshold_ms:
        return False
    if session.nudge_presented_count >= policy.max_nudges_per_tutor_turn:
        return False
    if session.nudge_generated_count >= policy.generated_nudge_rate_limit:
        return False
    if session.last_nudge_generated_at is None:
        return True
    cooldown_ms = int((now - session.last_nudge_generated_at).total_seconds() * 1000)
    return cooldown_ms >= policy.cooldown_ms


def _nudge_response(
    request: InteractionRequest,
    session: SessionRecord,
    message: str,
    status: Literal["GENERATED", "PRESENTED"] | None,
    state_updates: dict[str, object],
) -> InteractionResponse:
    updated_session = update_side_channel_state(session, state_updates)
    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=request.turn_id or "TURN-0000",
        interaction_type=request.interaction_type,
        nudge_id=request.nudge_id,
        session=updated_session,
        message=message,
        message_voice=message,
        visual_cue=None,
        scaffold_steps=updated_session.scaffold_steps,
        session_summary=None,
        conversation_action="WAIT_FOR_STUDENT",
        attempt_increment=0,
        status="NUDGE_SUPPRESSED" if status is None else None,
        retry_safe=True,
    )
    delivery = (
        NudgeDelivery(
            interaction_id=(
                request.turn_id if status == "GENERATED" else (request.nudge_id or request.turn_id)
            ),
            status=status,
            message=message,
        )
        if status is not None
        else None
    )


    return _cache_response(
        request,
        response.model_copy(
            update={
                "accepted_turn_id": request.turn_id,
                "nudge_delivery": delivery,
            }
        ),
    )


def _claim_inactivity_nudge(
    request: InteractionRequest,
    session: SessionRecord,
) -> InteractionResponse:
    now = datetime.now(timezone.utc)
    base_updates: dict[str, object] = {}
    if not _nudge_eligible(session, now):
        return _nudge_response(
            request,
            session,
            "",

            None,
            base_updates,
        )
    message = _contextual_nudge_message(session)
    return _nudge_response(
        request,
        session,
        message,
        "GENERATED",
        {
            **base_updates,
            "nudge_generated_count": session.nudge_generated_count + 1,
            "last_nudge_generated_at": now,
            "pending_nudge_id": request.turn_id,
            "pending_nudge_message": message,
        },
    )


def _acknowledge_inactivity_nudge(
    request: InteractionRequest,
    session: SessionRecord,
) -> InteractionResponse:
    if (
        request.nudge_id != session.pending_nudge_id
        or session.pending_nudge_message is None
    ):
        raise HTTPException(
            status_code=409,
            detail="UNKNOWN_NUDGE: nudge_id does not name the pending generated nudge.",
        )
    rules = load_classifier_rules()
    history = [
        *session.conversation_history,
        ConversationMessage(role="assistant", content=session.pending_nudge_message),
    ]
    if rules.conversation_rules.max_recent_messages == 0:
        history = []
    else:
        history = history[-rules.conversation_rules.max_recent_messages :]
    return _nudge_response(
        request,
        session,
        session.pending_nudge_message,
        "PRESENTED",
        {
            "nudge_presented_count": session.nudge_presented_count + 1,
            "pending_nudge_id": None,
            "pending_nudge_message": None,
            "conversation_history": history,
        },
    )


def _recorded_misconception(
    session: SessionRecord,
    selected_error_code: str | None,
) -> RecordedMisconception | None:
    if selected_error_code is None:
        return None
    for potential_error in _schema_question(session).tutor_view.potential_errors:
        error_code = potential_error.get("error_code")
        description = potential_error.get("description") or potential_error.get(
            "error_description"
        )
        if error_code == selected_error_code and isinstance(description, str):
            return RecordedMisconception(
                error_code=selected_error_code,
                description=description,
            )
    raise RuntimeError(
        f"Selected error {selected_error_code} has no current question metadata."
    )


def _active_scaffold_for_explain_again(
    session: SessionRecord,
) -> ActiveScaffoldState | None:
    if (
        session.scaffold_id is None
        or session.current_scaffold_step_id is None
        or session.scaffold_step_number < 1
        or session.scaffold_total_steps < 1
        or not session.scaffold_steps
    ):
        return None
    return ActiveScaffoldState(
        scaffold_id=session.scaffold_id,
        current_step_id=session.current_scaffold_step_id,
        step_number=session.scaffold_step_number,
        total_steps=session.scaffold_total_steps,
        step_text=session.scaffold_steps[0],
        step_voice=session.scaffold_steps[0],
    )


def _visible_visual_cue_for_explain_again(
    visual_cue: VisualCue | None,
) -> AIVisibleVisualCue | None:
    if visual_cue is None:
        return None
    presentation_types = {
        "EQUATION_BLOCK",
        "NUMBER_LINE",
        "GRAPH",
        "TABLE",
        "HIGHLIGHTED_STEP",
        "CONCEPT_CARD",
    }
    cue_type = (
        visual_cue.cue_type
        if visual_cue.cue_type in presentation_types
        else None
    )
    cue_id = visual_cue.cue_id or (
        visual_cue.cue_type if cue_type is None else None
    )
    return AIVisibleVisualCue(
        show=visual_cue.show,
        cue_id=cue_id,
        cue_type=cue_type,
        description=visual_cue.description,
        actions=visual_cue.actions,
    )


def _explain_again_interaction_response(
    request: InteractionRequest,
    session: SessionRecord,
) -> InteractionResponse:
    if session.current_phase != "GUIDED_PRACTICE":
        raise HTTPException(
            status_code=409,
            detail="EXPLAIN_AGAIN is currently available only in Guided Practice.",
        )
    if session.question_id is None or session.current_question is None:
        raise HTTPException(
            status_code=409,
            detail="EXPLAIN_AGAIN requires an active question.",
        )
    answer_spec = _active_answer_spec(session)
    context = _phase_2_prompt_context(session)
    if answer_spec is None or context is None:
        raise HTTPException(
            status_code=409,
            detail="EXPLAIN_AGAIN requires the active Guided Practice answer contract.",
        )
    rules = load_classifier_rules()
    openai_client = build_openai_ai_engine_client(get_settings())
    if openai_client is None:
        raise AdapterError(
            "openai_ai_engine",
            "Explain Again requires an enabled OpenAI AI-engine client.",
        )
    rubric = resolve_guided_rubric(
        question_id=session.question_id,
        question_type=session.question_type,
        question=session.current_question,
        answer_spec=answer_spec,
        potential_errors=guided_error_definitions(context.potential_errors),
        target_micro_skill_ids=context.target_micro_skill_ids,
        existing_rubric=session.generated_question_rubric,
        rules=rules,
        openai_client=openai_client,
    )
    objective = session.active_teaching_objective or initial_guided_objective(rubric)
    if not objective.missing_concept_ids:
        raise HTTPException(
            status_code=409,
            detail="EXPLAIN_AGAIN has no unresolved Guided Practice component.",
        )
    visual_cue = (
        _schema_visual_cue(session.student_model_event)
        if session.show_visual_cue
        else None
    )
    active_support_level, highest_support_used = _guided_support_levels(session)
    recorded_misconception = _recorded_misconception(
        session,
        session.selected_error_code,
    )
    result = generate_explain_again_response(
        ExplainAgainRequest(
            question_id=session.question_id,
            question=session.current_question,
            answer_spec=answer_spec,
            generated_question_rubric=rubric,
            active_teaching_objective=objective,
            first_unresolved_concept_id=objective.missing_concept_ids[0],
            guided_student_state=session.guided_student_state,
            selected_error_code=session.selected_error_code,
            recorded_misconception=recorded_misconception,
            recent_conversation=session.conversation_history,
            active_support_level=active_support_level,
            highest_support_used=highest_support_used,
            visible_visual_cue=_visible_visual_cue_for_explain_again(visual_cue),
            active_scaffold=_active_scaffold_for_explain_again(session),
            answer_reveal_allowed=False,
        )
    )
    if result.progression_change_requested:
        raise RuntimeError("Explain Again requested a forbidden progression change.")
    history = [
        *session.conversation_history,
        ConversationMessage(role="assistant", content=result.tutor_message),
    ]
    max_messages = rules.conversation_rules.max_recent_messages
    if max_messages == 0:
        history = []
    else:
        history = history[-max_messages:]
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
        {
            **_turn_updates(request, "ASKED_QUESTION", "ANSWER"),
            "conversation_history": history,
        },
    )
    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=request.turn_id or "TURN-0000",
        interaction_type=request.interaction_type,
        nudge_id=request.nudge_id,
        session=updated_session,
        message=result.tutor_message,
        message_voice=result.tutor_message_voice_optimised,
        visual_cue=visual_cue,
        scaffold_steps=updated_session.scaffold_steps,
        session_summary=None,
        conversation_action="ASK_QUESTION",
        attempt_increment=0,
        status=None,
        retry_safe=True,
    ).model_copy(
        update={
            "guided_student_state": result.guided_student_state,
            "active_teaching_objective": result.active_teaching_objective,
            "first_unresolved_concept_id": result.first_unresolved_concept_id,
            "selected_error_code": result.selected_error_code,
            "evaluation_reason_code": result.evaluation_reason_code,
            "support_served_this_turn": None,
            "active_support_level": result.active_support_level,
            "highest_support_used": result.highest_support_used,
            "active_scaffold": (
                result.active_scaffold.model_dump()
                if result.active_scaffold is not None
                else None
            ),
        }
    )
    return _cache_response(request, response)


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

    if session.current_phase == "INDEPENDENT_PRACTICE":
        if request.interaction_type == "CLARIFICATION_REQUEST":
            response = _response_from(
                session_id=request.session_id,
                student_id=request.student_id,
                turn_id=request.turn_id or "TURN-0000",
                interaction_type=request.interaction_type,
                nudge_id=None,
                session=session,
                message="Please use the canvas or an approved choice to record your answer.",
                message_voice="",
                visual_cue=None,
                scaffold_steps=[],
                session_summary=None,
                conversation_action="REQUEST_CLARIFICATION",
                attempt_increment=0,
                status="CLARIFICATION_REQUIRED",
                retry_safe=True,
            )
            return _cache_response(request, response)
        if request.interaction_type in {"HELP_REQUEST", "SUPPORT_REPLAY", "EXPLAIN_AGAIN"}:
            raise HTTPException(status_code=409, detail="Teaching support is unavailable during Independent Practice.")
        if request.interaction_type == "ANSWER_SUBMISSION":
            if request.input_source == "VOICE":
                raise HTTPException(status_code=409, detail="Voice cannot submit an Independent Practice answer.")
            if request.input_source != "CHOICE":
                raise HTTPException(
                    status_code=409,
                    detail="Independent Practice answers must use Canvas or Choice.",
                )
            require_phase3_submission(
                session,
                request.phase3_submission_confirmed,
                request.phase3_submission_kind,
                request.selected_option_id,
            )

    if request.interaction_type == "HELP_REQUEST" or _is_explicit_help_request(request):
        return await _guided_help_response(request, session, access_token)
    if request.interaction_type == "SUPPORT_REPLAY":
        support_message = _active_support_message(session)
        if support_message is None:
            raise HTTPException(
                status_code=409,
                detail="NO_ACTIVE_SUPPORT: this session has no support to replay.",
            )
        return _side_channel_response(
            request,
            session,
            support_message,
            support_message,
            "GIVE_HINT",
            _tutor_side_channel_updates(request, session, support_message),
        )
    if request.interaction_type == "EXPLAIN_AGAIN":
        return _explain_again_interaction_response(request, session)
    if request.interaction_type == "INACTIVITY_NUDGE":
        nudge_res = _claim_inactivity_nudge(request, session)
        return nudge_res

    if request.interaction_type == "NUDGE_PRESENTED":
        return _acknowledge_inactivity_nudge(request, session)


    student_message = _student_message_from(request)
    rules: ClassifierRulesConfig = load_classifier_rules()
    canvas_evidence = await _canvas_evidence_for(request)

    canvas_complete_correct = _is_complete_correct_canvas(
        canvas_evidence.ocr if canvas_evidence is not None else None,
        session.correct_answer,
    )
    if (
        request.input_source == "VOICE"
        and request.transcript_confidence is not None
        and request.transcript_confidence < rules.low_transcript_confidence_threshold
        and not canvas_complete_correct
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
            canvas_evidence.submission_id if canvas_evidence is not None else request.canvas_snapshot_id,
            canvas_evidence.ocr if canvas_evidence is not None else None,
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
                session_id=request.session_id,
                student_id=request.student_id,
                turn_id=request.turn_id or "TURN-0000",
                interaction_type=request.interaction_type,
                nudge_id=request.nudge_id,
                session=updated_session,
                message=_LOW_CONFIDENCE_MESSAGE,
                message_voice=_LOW_CONFIDENCE_MESSAGE,
                visual_cue=None,
                scaffold_steps=[],
                session_summary=None,
                conversation_action="REQUEST_CLARIFICATION",
                attempt_increment=0,
                status="CLARIFICATION_REQUIRED",
                retry_safe=None,
            ).model_copy(
                update={
                    "ocr": canvas_evidence.ocr if canvas_evidence is not None else None,
                    "snapshot_reference": (
                        canvas_evidence.snapshot_reference
                        if canvas_evidence is not None
                        else None
                    ),
                    "is_canvas_solution_correct": (
                        False
                        if canvas_evidence is not None
                        and not canvas_evidence.ocr.needs_clarification
                        else None
                    ),
                    "feedback_type": "CLARIFICATION",
                }
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
    ocr = (
        canvas_evidence.ocr
        if canvas_evidence is not None
        else canvas_submission.ocr
        if canvas_submission is not None
        else None
    )
    canvas_solution_complete_candidate = _is_complete_correct_canvas(
        ocr,
        session.correct_answer,
    )
    if (
        canvas_evidence is not None
        and canvas_solution_complete_candidate
        and _spoken_answer_conflicts_with_canvas(student_message, ocr.final_answer)
    ):
        message = (
            "Your board shows a correct final answer, but I heard a different answer. "
            "Which answer would you like me to check?"
        )
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session,
            session.current_phase,
            session.hint_count,
            session.current_phase,
            request.transcript_confidence,
            canvas_evidence.submission_id,
            ocr,
            False,
            False,
            [],
            {
                "attempt_count": session.attempt_count,
                "question_completed": session.question_completed,
                "conversation_history": _updated_conversation_history(
                    session.conversation_history,
                    student_message,
                    message,
                    rules.conversation_rules.max_recent_messages,
                ),
                **_turn_updates(request, "REQUESTED_CLARIFICATION", "CLARIFICATION"),
            },
        )
        return _cache_response(
            request,
            _response_from(
                session_id=request.session_id,
                student_id=request.student_id,
                turn_id=request.turn_id or "TURN-0000",
                interaction_type=request.interaction_type,
                nudge_id=request.nudge_id,
                session=updated_session,
                message=message,
                message_voice=message,
                visual_cue=None,
                scaffold_steps=[],
                session_summary=None,
                conversation_action="REQUEST_CLARIFICATION",
                attempt_increment=0,
                status="CLARIFICATION_REQUIRED",
                retry_safe=None,
            ).model_copy(
                update={
                    "ocr": ocr,
                    "snapshot_reference": canvas_evidence.snapshot_reference,
                    "is_canvas_solution_correct": True,
                    "feedback_type": "CLARIFICATION",
                }
            ),
        )
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
        canvas_mathml_blocks=ocr.mathml_blocks if ocr is not None else [],
        spatial_tokens=(canvas_evidence.spatial_tokens if canvas_evidence is not None else []),
        has_canvas_evidence=canvas_evidence is not None,
        canvas_solution_complete_candidate=canvas_solution_complete_candidate,
    )
    if ocr is not None and ocr.needs_clarification:
        message = "I’m having trouble reading your working on the board. Please rewrite it clearly and try again."
        updated_session = update_interaction_state(
            request.session_id,
            request.student_id,
            session,
            session.current_phase,
            session.hint_count,
            session.current_phase,
            request.transcript_confidence,
            canvas_evidence.submission_id if canvas_evidence is not None else request.canvas_snapshot_id,
            ocr,
            False,
            False,
            [],
            {
                "attempt_count": session.attempt_count,
                "question_completed": session.question_completed,
                "conversation_history": _updated_conversation_history(
                    session.conversation_history,
                    student_message,
                    message,
                    rules.conversation_rules.max_recent_messages,
                ),
                **_turn_updates(request, "REQUESTED_CLARIFICATION", "CLARIFICATION"),
            },
        )
        return _cache_response(
            request,
            _response_from(
                session_id=request.session_id,
                student_id=request.student_id,
                turn_id=request.turn_id or "TURN-0000",
                interaction_type=request.interaction_type,
                nudge_id=request.nudge_id,
                session=updated_session,
                message=message,
                message_voice=message,
                visual_cue=None,
                scaffold_steps=[],
                session_summary=None,
                conversation_action="REQUEST_CLARIFICATION",
                attempt_increment=0,
                status="CLARIFICATION_REQUIRED",
                retry_safe=None,
            ).model_copy(
                update={
                    "ocr": ocr,
                    "snapshot_reference": (
                        canvas_evidence.snapshot_reference
                        if canvas_evidence is not None
                        else None
                    ),
                    "feedback_type": "CLARIFICATION",
                }
            ),
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
                session_id=request.session_id,
                student_id=request.student_id,
                turn_id=request.turn_id or "TURN-0000",
                interaction_type=request.interaction_type,
                nudge_id=request.nudge_id,
                session=updated_session,
                message=fallback,
                message_voice=fallback,
                visual_cue=None,
                scaffold_steps=[],
                session_summary=None,
                conversation_action="WAIT_FOR_STUDENT",
                attempt_increment=0,
                status=None,
                retry_safe=None,
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

    schema_support_action: ConversationAction | None = None
    schema_support_level: SupportUsed | None = None
    support_payload = (
        schema_content_response.phase_payload.support_to_serve
        if schema_content_response is not None
        and schema_content_response.phase_payload is not None
        else None
    )
    if (
        support_payload is not None
        and support_payload.get("support_type") != "RETRY_WITHOUT_SUPPORT"
    ):
        (
            schema_support_message,
            schema_support_visual_cue,
            schema_support_steps,
            schema_support_action,
            schema_support_level,
        ) = _support_presentation(schema_content_response)
    else:
        schema_support_message = None
        schema_support_visual_cue = None
        schema_support_steps = []
    visual_cue = schema_support_visual_cue or _schema_visual_cue(schema_content_response) or (
        tutor.visual_cue if tutor.visual_cue.show else None
    )
    schema_hint = _schema_hint(schema_content_response)
    schema_steps = schema_support_steps or _schema_support_steps(schema_content_response)
    for scaffold_prompt in schema_steps:
        _validate_scaffold_prompt(scaffold_prompt, session.correct_answer, rules)
    scaffold_steps = schema_steps or tutor.scaffold_steps_delivered
    tutor_message = schema_support_message or _contextual_schema_hint(
        schema_hint,
        tutor.tutor_message,
    )
    tutor_message_voice = schema_support_message or _contextual_schema_hint(
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
            turn_session.correct_answer or "",
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
    if schema_support_action is not None:
        conversation_action = schema_support_action
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
        "wrong_attempt_count": (
            session.wrong_attempt_count + 1
            if not scaffold_turn and _is_support_failure(tutor)
            else 0
            if tutor.guided_student_state == "CORRECT"
            else session.wrong_attempt_count
        ),
        # A misconception belongs to the answer that demonstrated it. Keeping
        # the previous code when the current evaluation returns none makes a
        # corrected answer inherit stale feedback such as "you multiplied".
        # Side-channel turns do not pass through this state update, so clearing
        # here cannot affect Explain Again or inactivity requests.
        "selected_error_code": tutor.selected_error_code,
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
        state_updates["wrong_attempt_count"] = 0
        state_updates["selected_error_code"] = None
        state_updates["generated_question_rubric"] = None
        state_updates["active_teaching_objective"] = None
        state_updates["explanation_request_count"] = 0

    # Never turn repeated unresolved reasoning into a correct completion during
    # Guided Practice. A previous loop-breaker advanced after three explanation
    # requests even when answer_value_confirmed was false, allowing an incorrect
    # response to move to the next question. Guided progression must remain
    # evidence-driven; repetition alone is not evidence.
    if conversation_action == "REQUEST_EXPLANATION" and schema_response is None:
        answer_value_confirmed = (
            session.answer_value_confirmed or tutor.answer_value_confirmed
        )
        if _may_force_complete_repeated_explanation(
            turn_session.current_phase,
            answer_value_confirmed,
            session.explanation_request_count,
        ):
            conversation_action = "ADVANCE_TO_NEXT_QUESTION"
            state_updates["explanation_request_count"] = 0
            state_updates["question_completed"] = True
        else:
            state_updates["explanation_request_count"] = min(
                session.explanation_request_count + 1,
                2,
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
                hint_level_used=tutor.hint_level or 0,
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
        resulting_question_type = state_updates.get(
            "question_type",
            turn_session.question_type,
        )
        guided_question_type: QuestionType | None = (
            cast(QuestionType, resulting_question_type)
            if resulting_question_type in {
                "SINGLE_CHOICE",
                "SHORT_RESPONSE",
                "MULTI_PART_SHORT_RESPONSE",
                "CHOICE_WITH_EXPLANATION",
                "TRUE_FALSE_WITH_EXPLANATION",
            }
            else None
        )
        tutor_message = (
            guided_question_opening(
                resulting_question,
                guided_question_type,
                "Nice work. Here is the next question.",
            )
            if session.current_phase == "GUIDED_PRACTICE"
            else rules.messages.NEXT_QUESTION.format(
                question=resulting_question.strip()
            )
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
        canvas_evidence.submission_id if canvas_evidence is not None else request.canvas_snapshot_id,
        ocr,
        visual_cue is not None,
        len(scaffold_steps) > 0,
        scaffold_steps,
        state_updates,
    )

    response = _response_from(
        session_id=request.session_id,
        student_id=request.student_id,
        turn_id=request.turn_id or "TURN-0000",
        interaction_type=request.interaction_type,
        nudge_id=request.nudge_id,
        session=updated_session,
        message=tutor_message,
        message_voice=tutor_message_voice,
        visual_cue=visual_cue,
        scaffold_steps=scaffold_steps,
        session_summary=None,
        conversation_action=conversation_action,
        attempt_increment=effective_attempt_increment,
        status=None,
        retry_safe=None,
        previous_phase=session.current_phase if new_phase is not None else None,
    )
    guided_rescue = _guided_rescue(schema_content_response)
    support_served: SupportUsed | None = (
        schema_support_level or response.active_support_level
        if schema_content_response is not None
        and schema_content_response.phase_payload is not None
        and schema_content_response.phase_payload.support_to_serve is not None
        else guided_rescue.rescue_type
        if guided_rescue is not None
        else None
    )
    response = response.model_copy(
        update={
            "guided_rescue": guided_rescue,
            "active_support_level": (
                guided_rescue.rescue_type
                if guided_rescue is not None
                else response.active_support_level
            ),
            "guided_student_state": tutor.guided_student_state,
            "selected_error_code": tutor.selected_error_code,
            "evaluation_reason_code": (
                _evaluation_reason(tutor)
            ),
            "routing_reason_code": (
                schema_content_response.routing.reason_code
                if schema_content_response is not None
                else None
            ),
            "support_reason_code": (
                _WRONG_ESCALATION_BY_COUNT[
                    min(updated_session.wrong_attempt_count, 4)
                ]
                if _is_support_failure(tutor)
                and updated_session.wrong_attempt_count > 0
                else schema_content_response.routing.reason_code
                if support_served is not None
                else None
            ),
            "support_served_this_turn": support_served,
            "wrong_attempt_count": updated_session.wrong_attempt_count,
            "intervention_triggered": (
                _is_support_failure(tutor)
                and updated_session.wrong_attempt_count >= 4
            ),
            "ocr": ocr,
            "snapshot_reference": (
                canvas_evidence.snapshot_reference
                if canvas_evidence is not None
                else None
            ),
            "canvas_draw": (
                plan_canvas_draw(
                    tutor,
                    ocr.detected_regions,
                    canvas_evidence.spatial_tokens if canvas_evidence is not None else None,
                )
                if ocr is not None
                else []
            ),
            "is_canvas_solution_correct": (
                True
                if canvas_evidence is not None
                and canvas_solution_complete_candidate
                and tutor.evaluation == "CORRECT"
                else False
                if canvas_evidence is not None
                else None
            ),
            "advance_to_next_question": (
                schema_response is not None
                and conversation_action == "ADVANCE_TO_NEXT_QUESTION"
            ),
            "feedback_type": (
                "PRAISE"
                if tutor.evaluation == "CORRECT"
                or (
                    canvas_evidence is not None
                    and tutor.mistake_classification is not None
                    and tutor.mistake_classification.status == "no_mistake"
                )
                else "CORRECTION"
                if tutor.evaluation in {"INCORRECT", "PARTIALLY_CORRECT"}
                else "HINT"
            ),
        }
    )
    if turn_session.current_phase == "INDEPENDENT_PRACTICE":
        response = response.model_copy(
            update={
                "message_voice": "",
                "selected_error_code": None,
                "evaluation_reason_code": None,
                "routing_reason_code": None,
                "support_reason_code": None,
                "support_served_this_turn": None,
                "active_support_level": "NONE",
                "highest_support_used": "NONE",
                "wrong_attempt_count": 0,
                "intervention_triggered": False,
                "ocr": None,
                "canvas_draw": [],
                "is_canvas_solution_correct": None,
                "feedback_type": None,
            }
        )
    return _cache_response(request, response)
