from app.models.adapters import VisualCue
from app.models.fields import Phase
from app.models.student_model_session import (
    JourneyPhaseState,
    StudentModelCoreState,
    StudentModelPhase,
    StudentModelSessionEventResponse,
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


def schema_support_steps(
    event: StudentModelSessionEventResponse | None,
) -> list[str]:
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
    )
