from fastapi import HTTPException

from app.models.guided_learning import (
    ActiveGuidedRescue,
    GuidedRescue,
    GuidedRescueContext,
    TutorCanvasAction,
)


def _rescue_steps(rescue: GuidedRescue, request_id: str) -> tuple[str, str, list[str]]:
    if rescue.rescue_type == "PARALLEL_EXAMPLE":
        example = rescue.parallel_example
        if example is None:
            raise HTTPException(status_code=409, detail="Parallel rescue content is missing.")
        steps = [example.problem, *example.worked_steps]
        if not steps or steps[-1].strip().rstrip(".") != example.final_answer.strip().rstrip("."):
            steps.append(example.final_answer)
        return (
            example.parallel_example_id,
            example.parallel_example_id,
            steps,
        )
    solved = rescue.tutor_solved
    if solved is None:
        raise HTTPException(status_code=409, detail="Tutor-Solved rescue content is missing.")
    steps = solved.answer_steps or [solved.explanation]
    return (f"TUTOR_SOLVED:{request_id}:{rescue.micro_skill_id}", rescue.micro_skill_id, steps)


def active_rescue_from(
    question_id: str,
    rescue: GuidedRescue,
    canonical_answer: str,
    request_id: str,
) -> ActiveGuidedRescue:
    rescue_id, source_id, steps = _rescue_steps(rescue, request_id)
    if not steps or any(len(step.strip()) == 0 for step in steps):
        raise HTTPException(status_code=409, detail="Rescue content is empty.")
    if rescue.rescue_type == "TUTOR_SOLVED" and canonical_answer.strip():
        premature_reveal = any(
            canonical_answer.casefold() in step.casefold() for step in steps[:-1]
        )
        if premature_reveal:
            raise HTTPException(
                status_code=409,
                detail="Tutor-Solved rescue reveals the canonical answer before its final step.",
            )
    return ActiveGuidedRescue(
        question_id=question_id,
        rescue_id=rescue_id,
        source_id=source_id,
        rescue_type=rescue.rescue_type,
        steps=steps,
        return_target_object_id=f"TUTOR_ANCHOR:QUESTION:{question_id}",
        final_reveal_approved=rescue.rescue_type == "TUTOR_SOLVED",
        pending_phase3_transition=rescue.rescue_type == "TUTOR_SOLVED",
    )


def acknowledge_active_rescue(
    active: ActiveGuidedRescue,
    action_id: str,
    target_object_id: str,
) -> ActiveGuidedRescue:
    if action_id != active.current_action_id or target_object_id != active.current_target_object_id:
        raise HTTPException(status_code=409, detail="Rescue render acknowledgement does not match the active step.")
    if action_id in active.rendered_action_ids:
        return active
    return active.model_copy(update={"rendered_action_ids": [*active.rendered_action_ids, action_id]})


async def advance_active_rescue(
    active: ActiveGuidedRescue,
    question_id: str,
    rescue_id: str,
    current_step_index: int,
) -> ActiveGuidedRescue:
    if question_id != active.question_id or rescue_id != active.rescue_id:
        raise HTTPException(status_code=409, detail="Rescue advance does not own the active rescue.")
    if current_step_index < active.current_step_index:
        return active
    if current_step_index > active.current_step_index:
        raise HTTPException(status_code=409, detail="Rescue advance uses a future step index.")
    if active.current_action_id not in active.rendered_action_ids:
        raise HTTPException(status_code=409, detail="Rescue advance requires the current render acknowledgement.")
    if active.is_final_step:
        raise HTTPException(status_code=409, detail="Rescue is already at its final step.")
    return active.model_copy(update={"current_step_index": active.current_step_index + 1})


def rescue_context_for(active: ActiveGuidedRescue) -> GuidedRescueContext:
    return GuidedRescueContext(
        rescue_id=active.rescue_id,
        rescue_type=active.rescue_type,
        source_id=active.source_id,
        current_step_index=active.current_step_index,
        total_steps=len(active.steps),
        current_step_text=active.steps[active.current_step_index - 1],
        is_final_step=active.is_final_step,
        approved_answer_reveal=active.final_reveal_approved and active.is_final_step,
        return_target_object_id=active.return_target_object_id,
        active_support=active.rescue_type,
        active_action_ids=active.rendered_action_ids,
    )


def rescue_action_for(active: ActiveGuidedRescue) -> TutorCanvasAction:
    context = rescue_context_for(active)
    return TutorCanvasAction(
        action_id=active.current_action_id,
        type=(
            "SHOW_PARALLEL"
            if active.rescue_type == "PARALLEL_EXAMPLE"
            else "TUTOR_SOLVED_STEP"
        ),
        target_kind="TUTOR_ANCHOR",
        target_object_id=active.current_target_object_id,
        confirmed_component_id=None,
        text=context.current_step_text,
        source_id=active.source_id,
        answer_reveal_allowed=context.approved_answer_reveal,
        rescue_id=active.rescue_id,
        step_index=active.current_step_index,
        total_steps=len(active.steps),
        presentation_mode=(
            "PARALLEL" if active.rescue_type == "PARALLEL_EXAMPLE" else "TUTOR_SOLVED"
        ),
        return_target_object_id=active.return_target_object_id,
    )
