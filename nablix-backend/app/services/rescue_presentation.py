"""Rescue and scaffold presentation and evaluation rules.

Assembles the complete presentation rungs for Guided Rescue (Parallel Example,
Tutor-Solved), validates answer reveals, evaluates scaffold step responses,
and projects scaffold and visual-cue state for re-expression.
"""

from dataclasses import dataclass
import re
from typing import Final, Literal, TYPE_CHECKING

from fastapi import HTTPException
from pydantic import ValidationError

from app.ai_engine.classifier import (
    build_openai_ai_engine_client,
    contains_answer_reveal,
    normalize_exact_notation,
)
from app.ai_engine.classifier_config import (
    CanvasRescueWordingConfig,
    ClassifierRulesConfig,
)
from app.ai_engine.schemas import (
    ActiveScaffoldState,
    VisibleVisualCue as AIVisibleVisualCue,
)
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import (
    AnswerSpec,
    ScaffoldEvaluationContext,
    TutorResult,
    VisualCue,
)
from app.models.guided_learning import (
    ActiveGuidedRescue,
    ActiveScaffold,
    GuidedRescue,
    GuidedRescueContext,
    TutorCanvasAction,
)
from app.models.student_model_session import (
    StudentModelQuestion,
    StudentModelSessionEventResponse,
)
from app.services.student_model_session import (
    schema_active_support_steps as schema_support_steps,
    schema_hint,
    schema_visual_cue,
)
from app.services.canvas_annotations import rescue_tutor_wording
from app.services.student_model_session import schema_question

if TYPE_CHECKING:
    from app.models.session import SessionRecord

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

_SCAFFOLD_INTEGER_TOKEN: Final[str] = (
    r"-?\d+|" + "|".join(_NUMBER_WORD_VALUES)
)
_ADDITION_CHANGE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"(?:\+|(?<!\w)(?:plus|add(?:s|ed|ing)?(?:\s+by)?|"
    rf"increase(?:s|d|ing)?(?:\s+by)?))\s*"
    rf"(?P<operand>{_SCAFFOLD_INTEGER_TOKEN})(?!\w)",
    re.IGNORECASE,
)


def _active_answer_spec(session: "SessionRecord") -> AnswerSpec | None:
    try:
        return schema_question(session).answer_spec
    except HTTPException:
        return None


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
    request_id: str,
) -> ActiveGuidedRescue:
    """Assemble the rung. Answer-reveal safety is judged once, on the FINISHED
    steps -- see validate_rescue_reveal. Judging the authored steps here as well
    rejected Tutor-Solved content the response-aware writer was about to replace,
    and it did so after Student Model had already recorded the rung."""

    rescue_id, source_id, steps = _rescue_steps(rescue, request_id)
    if not steps or any(len(step.strip()) == 0 for step in steps):
        raise HTTPException(status_code=409, detail="Rescue content is empty.")
    return ActiveGuidedRescue(
        question_id=question_id,
        rescue_id=rescue_id,
        source_id=source_id,
        rescue_type=rescue.rescue_type,
        steps=steps,
        return_target_object_id=f"TUTOR_ANCHOR:QUESTION:{question_id}",
        final_reveal_approved=rescue.rescue_type == "TUTOR_SOLVED",
        pending_phase3_transition=False,
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


def guided_rescue(
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


def guided_rescue_message(rescue: GuidedRescue) -> str | None:
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


def written_rescue_steps(
    session: "SessionRecord", rescue: GuidedRescue, canonical_answer: str,
    rescue_id: str, rules: ClassifierRulesConfig,
) -> list[str]:
    """The response-aware rewrite of an authorised rung, one row per step."""

    client = build_openai_ai_engine_client(get_settings().model_copy(
        update={"openai_ai_engine_model": rules.guided_learning.model},
    ))
    if client is None:
        raise AdapterError("openai_ai_engine", "Worked presentation requires the configured Guided model.")
    presentation = client.write_guided_worked_presentation(
        support={
            "authorised_support": rescue.model_dump(),
            "question": session.current_question,
            "canonical_answer": canonical_answer,
            "identified_difficulty": (
                session.guided_teaching_state.identified_difficulty
                if session.guided_teaching_state is not None else None
            ),
        },
        system_prompt=rules.guided_learning.response_aware_worked_prompt,
    )
    final_answer = (
        rescue.parallel_example.final_answer
        if rescue.parallel_example is not None else canonical_answer
    )
    if normalize_exact_notation(presentation.steps[-1].expression) != normalize_exact_notation(final_answer):
        raise AdapterError("openai_ai_engine", "Worked presentation changed the authorised final answer.")
    steps = [f"{step.expression}\n{step.annotation}" for step in presentation.steps]
    logger.info("guided_worked_presentation_generated", extra={
        "question_id": session.question_id, "rescue_id": rescue_id,
        "step_count": len(steps), "provenance": "GENERATED",
    })
    return steps


def validate_rescue_reveal(
    active: ActiveGuidedRescue, canonical_answer: str, rules: ClassifierRulesConfig,
) -> None:
    """Judge answer reveal ONCE, on the steps that will actually be shown.

    Parallel Example never reveals the active answer; Tutor-Solved may reveal it
    only on its final step. Authored and generated steps are held to the same
    rule here, so neither can be judged twice -- which is what rejected authored
    Tutor-Solved content the writer was about to replace -- nor not at all.
    """

    forbidden = (
        active.steps if active.rescue_type == "PARALLEL_EXAMPLE" else active.steps[:-1]
    )
    if any(contains_answer_reveal(step, canonical_answer, rules) for step in forbidden):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{active.rescue_type} rescue reveals the active answer "
                "before authorisation."
            ),
        )


def presented_rescue(
    session: "SessionRecord", question_id: str | None, rescue: GuidedRescue | None,
    canonical_answer: str, request_id: str, rules: ClassifierRulesConfig,
) -> ActiveGuidedRescue | None:
    """Build the complete rung the student will see, or nothing.

    One place, because the presentation has to be finished BEFORE it is judged
    and both callers need the same order: assemble, rewrite, validate.
    """

    if (
        rescue is None
        or question_id is None
        or not rules.guided_learning.canvas_rescue_presentation_enabled
    ):
        return None
    active = active_rescue_from(question_id, rescue, request_id)
    existing = session.active_guided_rescue
    if existing is not None and existing.rescue_id == active.rescue_id:
        # Already built and already validated on the turn that served it.
        return existing
    if rules.guided_learning.response_aware_enabled:
        active = active.model_copy(update={"steps": written_rescue_steps(
            session, rescue, canonical_answer, active.rescue_id, rules,
        )})
    validate_rescue_reveal(active, canonical_answer, rules)
    return active


def tutor_with_guided_rescue(
    tutor: TutorResult,
    event: StudentModelSessionEventResponse,
    canvas_rescue_presentation_enabled: bool,
    canonical_answer: str,
    rescue_wording: CanvasRescueWordingConfig,
    persisted_rescue_context: GuidedRescueContext | None,
) -> TutorResult:
    rescue = guided_rescue(event)
    if rescue is None:
        return tutor
    rescue_context = persisted_rescue_context or rescue.tutor_engine_context
    if canvas_rescue_presentation_enabled and rescue_context is None:
        logger.warning(
            "guided_rescue_context_missing",
            extra={"request_id": event.request_id, "rescue_type": rescue.rescue_type},
        )
        return tutor
    message = (
        rescue_tutor_wording(rescue_context, canonical_answer, rescue_wording)
        if canvas_rescue_presentation_enabled and rescue_context is not None
        else guided_rescue_message(rescue)
    )
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
    approved_reveal = (
        rescue_context is not None
        and rescue_context.rescue_type == "TUTOR_SOLVED"
        and rescue_context.active_support == "TUTOR_SOLVED"
        and rescue_context.is_final_step
        and rescue_context.approved_answer_reveal
    )
    return tutor.model_copy(
        update={
            "response_strategy": (
                "PROVIDE_WORKED_EXAMPLE" if parallel else "TUTOR_SOLVED"
            ),
            "tutor_message": message,
            "tutor_message_voice": message,
            "voice_optimised": True,
            "answer_reveal_allowed": (
                approved_reveal
                if canvas_rescue_presentation_enabled
                else rescue.rescue_type == "TUTOR_SOLVED"
            ),
            "recommended_conversation_action": (
                "ASK_QUESTION" if parallel else "WAIT_FOR_STUDENT"
            ),
            "question_completed": (
                False
                if canvas_rescue_presentation_enabled and rescue_context is not None
                else not parallel
            ),
        }
    )


def validate_scaffold_prompt(
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


def schema_scaffold_state(
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


def active_scaffold_steps(session: "SessionRecord") -> list[dict[str, object]]:
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


def next_scaffold_state(
    session: "SessionRecord",
) -> tuple[str | None, dict[str, object]]:
    steps = active_scaffold_steps(session)
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


def completed_scaffold_state(session: "SessionRecord") -> dict[str, object]:
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


def normalize_scaffold_response(value: str) -> str:
    normalized = value.casefold().replace("−", "-").replace("⁄", "/")
    normalized = re.sub(r"(?<=[\d½⅓¼¾⅔⅛])(?=[a-z])", " ", normalized)
    normalized = re.sub(r"(?<=[a-z])(?=[\d½⅓¼¾⅔⅛])", " ", normalized)
    normalized = re.sub(r"[^\w/½⅓¼¾⅔⅛]+", " ", normalized)
    return " ".join(normalized.split())


def contains_scaffold_response(student: str, expected: str) -> bool:
    if expected == "":
        return False
    pattern = rf"(?<![\w/]){re.escape(expected)}(?![\w/])"
    return re.search(pattern, student) is not None


def addition_change_operand(value: str) -> str | None:
    match = _ADDITION_CHANGE_PATTERN.search(value)
    if match is None:
        return None
    operand = match.group("operand").casefold()
    if operand in _NUMBER_WORD_VALUES:
        return _NUMBER_WORD_VALUES[operand]
    return str(int(operand))


def matches_authored_scaffold_concept(
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
    if any(contains_scaffold_response(student, value) for value in alternatives):
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


def scaffold_response_is_correct(
    student_message: str,
    expected_response: str,
    tutor_evaluation: str,
    canonical_answer: str,
    rules: ClassifierRulesConfig,
) -> bool:
    normalized_student = normalize_scaffold_response(student_message)
    normalized_expected = normalize_scaffold_response(expected_response)
    aliases = next(
        (
            values
            for key, values in rules.scaffold_response_rules.aliases.items()
            if normalize_scaffold_response(key) == normalized_expected
        ),
        [],
    )
    accepted = {
        normalized_expected,
        *(normalize_scaffold_response(alias) for alias in aliases),
    }
    if any(contains_scaffold_response(normalized_student, value) for value in accepted):
        return True
    if matches_authored_scaffold_concept(
        normalized_student,
        normalized_expected,
        normalize_scaffold_response(canonical_answer),
    ):
        return True
    expected_addition = addition_change_operand(expected_response)
    student_addition = addition_change_operand(student_message)
    if expected_addition is not None and student_addition == expected_addition:
        return True
    return tutor_evaluation == "CORRECT"


def scaffold_evaluation_context(
    session: "SessionRecord",
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
    rubric = session.generated_question_rubric
    missing_component_ids = (
        set(session.guided_teaching_state.missing_component_ids)
        if session.guided_teaching_state is not None
        else set()
    )
    allowed_concepts = (
        [
            concept
            for concept in rubric.required_concepts
            if not missing_component_ids or concept.concept_id in missing_component_ids
        ]
        if rubric is not None
        else []
    )
    active_component_id = (
        session.guided_teaching_state.active_component_id
        if session.guided_teaching_state is not None
        else None
    )
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
        next_step_prompt=next_scaffold_state(session)[0],
        active_component_id=active_component_id,
        allowed_concepts=allowed_concepts,
    )


def scaffold_chat_line(reply: str, step: str) -> str:
    """Compose the tutor's evaluation with the next scaffold step into one line.

    The chat panel shows one message per turn. A scaffold turn has two lines --
    the evaluation of the step the student just answered and the prompt for
    the step it is asking next -- and the client had to append them separately,
    which is how every scaffold turn produced two chat bubbles and a voice line
    that matched neither. Composed here so both transports say the same sentence
    and the frontend appends exactly one message.
    """

    reply_text, step_text = reply.strip(), step.strip()
    if not step_text or step_text == reply_text:
        return reply
    return f"{reply_text} {step_text}".strip()


def active_scaffold(session: "SessionRecord") -> ActiveScaffold | None:
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


def active_scaffold_for_explain_again(
    session: "SessionRecord",
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


def visible_visual_cue_for_explain_again(
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



