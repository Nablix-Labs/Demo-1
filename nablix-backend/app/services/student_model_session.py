from typing import TYPE_CHECKING
from fastapi import HTTPException

from app.models.adapters import Phase2PromptContext, VisualCue
from app.models.fields import Phase
from app.models.student_model_session import (
    JourneyPhaseState,
    StudentModelCoreState,
    StudentModelPhase,
    StudentModelQuestion,
    StudentModelSessionEventResponse,
    SupportUsed,
)

if TYPE_CHECKING:
    from app.models.session import SessionRecord


SUPPORT_RANK: tuple[SupportUsed, ...] = (
    "NONE",
    "HINT",
    "VISUAL_CUE",
    "SCAFFOLD",
    "PARALLEL_EXAMPLE",
    "TUTOR_SOLVED",
)

PHASE_FROM_STUDENT_MODEL: dict[StudentModelPhase, Phase] = {
    "PHASE_0_DIAGNOSTIC": "DIAGNOSTIC",
    "PHASE_1_ORIENTATION": "CONCEPT_ORIENTATION",
    "PHASE_2_GUIDED_LEARNING": "GUIDED_PRACTICE",
    "PHASE_3_INDEPENDENT_PRACTICE": "INDEPENDENT_PRACTICE",
    "REVIEW": "REVIEW",
}


def schema_visual_cue(
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
        asset_url = item.get("asset_url")
        actions = item.get("actions", [])
        if not isinstance(content_id, str) or not isinstance(description, str):
            raise RuntimeError("Student Model returned a malformed visual cue.")
        if not isinstance(actions, list) or not all(
            isinstance(action, dict) for action in actions
        ):
            raise RuntimeError("Student Model returned malformed visual cue actions.")
        if asset_url is not None and not isinstance(asset_url, str):
            raise RuntimeError("Student Model returned a malformed visual cue asset URL.")
        return VisualCue(
            show=True,
            cue_id=content_id,
            cue_type=cue_type if isinstance(cue_type, str) else None,
            description=description,
            asset_url=asset_url,
            actions=actions,
        )
    return None


def schema_hint(event: StudentModelSessionEventResponse | None) -> str | None:
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


def schema_all_support_steps(
    event: StudentModelSessionEventResponse | None,
) -> list[str]:
    """Extract all catalog support and rescue steps for session initialization."""
    if event is None or event.phase_payload is None:
        return []
    support = event.phase_payload.support_to_serve
    if support is not None:
        steps = support.get("steps")
        if isinstance(steps, list):
            prompts: list[str] = []
            for step in steps:
                if isinstance(step, dict) and isinstance(step.get("prompt"), str):
                    prompts.append(step["prompt"])
            return prompts
    rescue = event.phase_payload.rescue_to_serve
    if rescue is None:
        return []
    result: list[str] = []
    parallel = rescue.get("parallel_example")
    if isinstance(parallel, dict):
        worked_steps = parallel.get("worked_steps")
        if isinstance(worked_steps, list):
            result.extend(step for step in worked_steps if isinstance(step, str))
    solved = rescue.get("tutor_solved")
    if isinstance(solved, dict) and isinstance(solved.get("explanation"), str):
        result.append(solved["explanation"])
    return result


schema_support_steps = schema_all_support_steps


def schema_active_support_steps(
    event: StudentModelSessionEventResponse | None,
) -> list[str]:
    """Extract the prompt for the active/current scaffold step."""
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
    return []


def _active_phase_state(
    event: StudentModelSessionEventResponse,
) -> JourneyPhaseState:
    journey = event.journey_state
    phase_states: dict[StudentModelPhase, JourneyPhaseState] = {
        "PHASE_0_DIAGNOSTIC": journey.phase_0_diagnostic,
        "PHASE_1_ORIENTATION": journey.phase_1_orientation,
        "PHASE_2_GUIDED_LEARNING": journey.phase_2_guided_learning,
        "PHASE_3_INDEPENDENT_PRACTICE": journey.phase_3_independent_practice,
        "REVIEW": journey.review,
    }
    effective_phase = journey.recommended_entry_phase or journey.current_phase
    return phase_states[effective_phase]


def project_student_model_state(
    event: StudentModelSessionEventResponse,
) -> StudentModelCoreState:
    """Flatten Saravanan's journey without duplicating its progression logic."""

    journey = event.journey_state
    active = _active_phase_state(event)
    guided = journey.phase_2_guided_learning
    independent = journey.phase_3_independent_practice
    return StudentModelCoreState(
        student_id=journey.student_id,
        topic_id=journey.topic_id,
        current_phase=journey.current_phase,
        mastery_status=journey.mastery_status,
        continuity_status=journey.continuity_status,
        recommended_entry_phase=journey.recommended_entry_phase,
        target_micro_skill_ids=active.target_micro_skill_ids,
        completed_micro_skill_ids=active.completed_micro_skill_ids,
        independently_verified_micro_skill_ids=independent.verified_micro_skill_ids,
        unresolved_micro_skill_ids=independent.unresolved_micro_skill_ids,
        highest_support_used_by_skill=guided.highest_support_used_by_skill,
        used_question_ids=active.used_question_ids,
        current_question_id=active.current_question_id,
        transition_reason=event.routing.reason,
        next_topic_recommendation=event.routing.next_topic_id,
        next_topic_entry_phase=event.routing.next_topic_entry_phase,
    )


def schema_question(session: "SessionRecord") -> StudentModelQuestion:
    event = session.student_model_event
    if event is None:
        raise HTTPException(
            status_code=409,
            detail="Schema 3.0 session state is missing.",
        )
    question_set = (
        event.phase_payload.question_set
        if event.phase_payload is not None
        else None
    )
    if question_set is None and session.active_student_model_question is not None:
        return session.active_student_model_question
    if question_set is None:
        raise HTTPException(status_code=503, detail="Student Model returned no active question set.")
    if session.question_id is None:
        raise HTTPException(
            status_code=409,
            detail="The current phase has no active question.",
        )
    question: StudentModelQuestion | None = next(
        (
            item
            for item in question_set.questions
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


def schema_question_mapped_micro_skills(session: "SessionRecord") -> list[str]:
    question = schema_question(session)
    skills = [mapping.micro_skill_id for mapping in question.micro_skill_mappings]
    if not skills:
        raise HTTPException(
            status_code=409,
            detail=f"Student Model returned no micro-skills for {session.question_id}.",
        )
    return skills


def schema_event_micro_skills(session: "SessionRecord") -> list[str]:
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema event skill lookup requires stored journey state.")
    if session.current_phase != "GUIDED_PRACTICE":
        return schema_question_mapped_micro_skills(session)
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


def schema_support_used(
    session: "SessionRecord",
    micro_skill_ids: list[str],
) -> SupportUsed:
    event = session.student_model_event
    if event is None:
        raise RuntimeError("Schema support lookup requires a stored Student Model event.")
    support_by_skill = (
        event.journey_state.phase_2_guided_learning.highest_support_used_by_skill
    )
    supports = [support_by_skill.get(skill, "NONE") for skill in micro_skill_ids]
    return max(supports, key=SUPPORT_RANK.index)


def phase_2_prompt_context(
    session: "SessionRecord",
) -> Phase2PromptContext | None:
    event = session.student_model_event
    if event is None or session.current_phase != "GUIDED_PRACTICE":
        return None
    question = schema_question(session)
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
            "support_catalog": question.tutor_view.support_catalog,
            "potential_errors": question.tutor_view.potential_errors,
        },
        potential_errors=question.tutor_view.potential_errors,
        support_catalog=question.tutor_view.support_catalog,
        current_support=support,
        current_scaffold_step_number=session.scaffold_step_number,
        consecutive_stuck_count=session.stuck_count,
    )
