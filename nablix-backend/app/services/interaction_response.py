"""Interaction response projection and replay routines.

Projects the wire InteractionResponse from persisted session state and
turn results, handles idempotency replays, stale turn responses,
and manages conversation state identities.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from app.models.adapters import (
    ConversationAction,
    ExpectedStudentResponse,
    TutorAction,
    TutorResult,
    VisualCue,
)
from app.models.fields import Phase
from app.models.guided_learning import PrerequisiteRepair
from app.models.interaction import (
    InteractionResponse,
    StaleTurnResponse,
)
from app.models.question_anchor import QuestionTextAnchor
from app.models.session import (
    SessionRecord,
    SessionSummary,
)
from app.models.student_model_session import (
    PublicStudentModelRouting,
    StudentModelSessionEventResponse,
    SupportUsed,
)
from app.services.phase_transition import (
    DEFAULT_TRANSITION_MESSAGE,
    TRANSITION_MESSAGES,
)
from app.services.question_anchors import plan_canvas_action_anchors
from app.services.rescue_presentation import (
    active_scaffold,
    scaffold_chat_line,
    schema_hint,
    schema_scaffold_state,
    schema_support_steps,
    schema_visual_cue,
)
from app.services.session_service import (
    inactivity_policy,
    independent_practice_is_halted,
    independent_practice_is_silent,
    nudge_delivery_for,
)
from app.services.student_model_session import SUPPORT_RANK

STALE_TURN_MESSAGE: str = (
    "The conversation has moved forward. Please use the latest tutor response."
)


@dataclass(frozen=True)
class Phase3TerminalAttempt:
    question_id: str
    outcome: Literal["INDEPENDENTLY_VERIFIED", "RESCUE_REQUIRED"]
    selected_error_code: str | None


def phase3_terminal_attempt(
    stored_event: StudentModelSessionEventResponse | None,
) -> Phase3TerminalAttempt | None:
    if stored_event is None or not isinstance(stored_event.event_result, dict):
        return None
    attempt = stored_event.event_result.get("attempt")
    if not isinstance(attempt, dict):
        return None
    question_id = attempt.get("question_id")
    evaluation = attempt.get("evaluation")
    if not isinstance(question_id, str) or evaluation not in {"CORRECT", "INCORRECT"}:
        return None
    outcome: Literal["INDEPENDENTLY_VERIFIED", "RESCUE_REQUIRED"] = (
        "INDEPENDENTLY_VERIFIED" if evaluation == "CORRECT" else "RESCUE_REQUIRED"
    )
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


def renderable_support_level(
    event: StudentModelSessionEventResponse,
) -> SupportUsed:
    """Return a support rung only when the response contains something to show."""
    payload = event.phase_payload
    support = payload.support_to_serve if payload is not None else None
    if support is None:
        return "NONE"

    support_type = support.get("support_type")
    hint = schema_hint(event)
    if support_type == "HINT":
        return "HINT" if hint is not None else "NONE"

    if support_type in {"VISUAL_CUE", "HINT_AND_VISUAL_CUE"}:
        if schema_visual_cue(event) is not None:
            return "VISUAL_CUE"
        return "HINT" if hint is not None else "NONE"

    if support_type == "SCAFFOLD":
        scaffold_state = schema_scaffold_state(event)
        has_scaffold = (
            bool(schema_support_steps(event))
            and scaffold_state.get("scaffold_id") is not None
            and scaffold_state.get("current_scaffold_step_id") is not None
            and scaffold_state.get("scaffold_expected_response") is not None
        )
        if has_scaffold:
            return "SCAFFOLD"
        return "HINT" if hint is not None else "NONE"

    return "NONE"


def guided_support_levels(session: SessionRecord) -> tuple[SupportUsed, SupportUsed]:
    stored_event = session.student_model_event
    guided = (
        stored_event.journey_state.phase_2_guided_learning
        if stored_event is not None
        else None
    )
    active_support_level = (
        renderable_support_level(stored_event)
        if stored_event is not None
        else "NONE"
    )
    highest_support_used: SupportUsed = (
        max(
            guided.highest_support_used_by_skill.values(),
            key=SUPPORT_RANK.index,
            default="NONE",
        )
        if guided is not None
        else "NONE"
    )
    return active_support_level, highest_support_used


def question_anchors(session: SessionRecord) -> list[QuestionTextAnchor]:
    """Keep question tokens addressable without rendering premature emphasis."""
    return plan_canvas_action_anchors(session.question_id, session.current_question)


def new_tutor_turn_id() -> str:
    return f"TUTOR-{uuid4()}"


def accepted_turn_identity(turn_id: str) -> dict[str, object]:
    """The identity the client gates on, for one accepted turn."""
    return {
        "last_processed_turn_id": turn_id,
        "last_tutor_turn_id": new_tutor_turn_id(),
        "last_tutor_response_at": datetime.now(timezone.utc),
    }


def turn_updates(
    turn_id: str,
    last_tutor_action: TutorAction,
    expected_student_response: ExpectedStudentResponse,
) -> dict[str, object]:
    return {
        "last_tutor_action": last_tutor_action,
        "expected_student_response": expected_student_response,
        **accepted_turn_identity(turn_id),
    }


def independent_attempt_updates(
    turn_session: SessionRecord,
    tutor: TutorResult,
) -> dict[str, object]:
    """Count one terminal Independent Practice result, or nothing."""
    if (
        turn_session.current_phase != "INDEPENDENT_PRACTICE"
        or not tutor.independent_attempt_terminal
    ):
        return {}
    return {
        "independent_attempt_count": turn_session.independent_attempt_count + 1
    }


def conversation_state_for(
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


def independent_correct_in_session(session: SessionRecord) -> int:
    """Unaided corrects in any phase."""
    return sum(
        attempt.evaluation == "CORRECT" and attempt.hint_level_used == 0
        for attempt in session.per_question_history
    )


def current_hint_level_from(hint_count: int) -> int | None:
    if hint_count <= 0:
        return None
    return min(hint_count, 3)


def next_hint_count_from(session: SessionRecord) -> int:
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


def stale_turn_response(session: SessionRecord) -> StaleTurnResponse:
    return StaleTurnResponse(
        status="STALE_TURN",
        accepted_turn_id=None,
        expected_previous_tutor_turn_id=session.last_tutor_turn_id,
        conversation_action="WAIT_FOR_STUDENT",
        attempt_increment=0,
        retry_safe=False,
        message=STALE_TURN_MESSAGE,
    )


def project_interaction_response(
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
    """Project the complete wire InteractionResponse for a turn."""
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
        if support_type in SUPPORT_RANK
        else "VISUAL_CUE"
        if support_type == "HINT_AND_VISUAL_CUE"
        else "NONE"
    )
    highest_support_used = (
        max(
            guided.highest_support_used_by_skill.values(),
            key=SUPPORT_RANK.index,
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
    phase3_attempt = phase3_terminal_attempt(stored_event)
    phase3_silent = (
        independent_practice_is_silent(session)
        and previous_phase != "GUIDED_PRACTICE"
        and session.intervention is None
    )
    if independent_practice_is_halted(session) and session.message.strip():
        message = session.message
        message_voice = session.message
    scaffold_is_renderable = (
        bool(scaffold_steps) and session.current_scaffold_step_id is not None
    )
    if phase3_silent and phase3_attempt is not None:
        outcome = phase3_attempt.outcome
        message = (
            "Answer recorded."
            if outcome == "INDEPENDENTLY_VERIFIED"
            else "We'll review this one before a fresh independent check."
        )
        message_voice = ""
        visual_cue = None
        scaffold_steps = []
    if not phase3_silent and scaffold_is_renderable:
        message = scaffold_chat_line(message, scaffold_steps[0])
        message_voice = scaffold_chat_line(message_voice, scaffold_steps[0])
    if previous_phase is not None and not message_voice.strip() and transition_message:
        message_voice = transition_message
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
        support_message=None,
        show_canvas=session.show_canvas,
        show_hint_button=False if phase3_silent else session.show_hint_button,
        show_visual_cue=False if phase3_silent else visual_cue is not None,
        visual_cue=None if phase3_silent else visual_cue,
        show_scaffold_panel=(
            False if phase3_silent else session.show_scaffold_panel and scaffold_is_renderable
        ),
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
        routing=(
            None
            if phase3_silent or stored_event is None
            else PublicStudentModelRouting.model_validate(stored_event.routing)
        ),
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
        question_anchors=[] if phase3_silent else question_anchors(session),
        question_opening_canvas_actions=[],
        wrong_attempt_count=session.wrong_attempt_count,
        intervention_triggered=session.wrong_attempt_count >= 4,
        intervention=session.intervention,
        content_gap_detected=session.content_gap_detected,
        routing_reason_code=(
            None
            if phase3_silent
            else
            stored_event.routing.reason_code if stored_event is not None else None
        ),
        active_scaffold=None if phase3_silent else active_scaffold(session),
        prerequisite_repair=(
            PrerequisiteRepair(
                prerequisite_micro_skill_ids=(
                    session.prerequisite_repair_event.routing.prerequisite_micro_skill_ids
                ),
                reason_code=session.prerequisite_repair_event.routing.reason_code,
            )
            if session.prerequisite_repair_event is not None
            else None
        ),
        inactivity_policy=inactivity_policy(),
        nudge_delivery=nudge_delivery,
        phase3_submission_confirmed=phase3_attempt is not None if phase3_silent else None,
        independent_outcome=(phase3_attempt.outcome if phase3_attempt else None),
        independent_success=(
            phase3_attempt.outcome == "INDEPENDENTLY_VERIFIED" if phase3_attempt else None
        ),
        independent_attempt_terminal=phase3_attempt is not None if phase3_silent else None,
        phase3_locked_question_id=(
            phase3_attempt.question_id if phase3_attempt else None
        ),
        selected_error_code=(
            None if phase3_silent else session.selected_error_code
        ),
        first_error_step=None,
        review_materialization_state=session.review_materialization_state,
    )


def replayed_turn_response(
    session: SessionRecord,
    turn_id: str,
) -> InteractionResponse:
    """Rebuild an accepted turn's answer from persisted session state alone."""
    return project_interaction_response(
        session_id=session.session_id,
        student_id=session.student_id,
        turn_id=turn_id,
        interaction_type="ANSWER_SUBMISSION",
        nudge_id=None,
        session=session,
        message=session.message,
        message_voice="",
        visual_cue=None,
        scaffold_steps=[],
        session_summary=None,
        conversation_action="WAIT_FOR_STUDENT",
        attempt_increment=0,
        status=None,
        retry_safe=True,
    )
