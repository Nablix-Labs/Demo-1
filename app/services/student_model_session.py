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
    return phase_states[journey.current_phase]


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
