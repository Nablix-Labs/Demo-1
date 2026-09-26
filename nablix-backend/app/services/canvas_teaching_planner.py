from __future__ import annotations

import re
from typing import Literal, TypedDict

from app.ai_engine.classifier import build_openai_ai_engine_client
from app.ai_engine.classifier_config import CanvasTeachingConfig, load_classifier_rules
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.core.logger import logger
from app.models.adapters import TutorResult
from app.models.canvas_teaching import (
    CanvasTeachingBeat,
    CanvasTeachingMode,
    CanvasTeachingOperation,
    CanvasTeachingPlan,
    CanvasTeachingPlanDraft,
    CanvasSpeechAnchor,
)
from app.models.question_anchor import QuestionTextAnchor


_PATTERN_CASE_RE = re.compile(
    r"(?P<starting>\d+)\s*(?P<operator>[+−×*\-])\s*(?P<fixed>\d+)"
)
_CANONICAL_PATTERN_RE = re.compile(
    r"(?P<variable>[a-z])\s*(?P<operator>[+−×*\-])\s*(?P<fixed>\d+)",
    re.IGNORECASE,
)


class PatternAddConstantScene(TypedDict):
    variable: str
    operator: str
    fixed_value: str
    changing_ids: list[str]
    fixed_ids: list[str]
    operator_ids: list[str]


def plan_canvas_teaching(
    question_id: str | None,
    question: str | None,
    source_turn_id: str | None,
    tutor_turn_id: str | None,
    scene_revision: int,
    tutor_message_voice: str,
    tutor: TutorResult | None,
    question_anchors: list[QuestionTextAnchor],
    student_response: str,
    canonical_answer: str | None,
    active_support_level: str | None,
    current_unresolved_component_id: str | None,
) -> CanvasTeachingPlan | None:
    """Create a visual-only Guided Practice plan from an already-final tutor turn."""

    rules = load_classifier_rules()
    config = rules.guided_learning.canvas_teaching
    if not config.enabled or question_id is None or question is None or tutor is None:
        return None
    if source_turn_id is None or not tutor_message_voice.strip():
        return None
    question_anchor_texts = {
        anchor.token_id: anchor.text for anchor in question_anchors
    }
    teaching_mode = _teaching_mode(tutor, active_support_level, config)
    if teaching_mode in config.suppressed_main_canvas_modes:
        return None

    allowed_targets = [anchor.token_id for anchor in question_anchors]
    allowed_targets.extend(["ZONE:QUESTION", "ZONE:REASONING", "ZONE:TUTOR_SOLUTION"])
    current_evidence = _current_turn_evidence(tutor)
    direct_explanation = (
        teaching_mode == "DIRECT_EXPLANATION"
        and _approved_direct_explanation(tutor, config)
    )
    tutor_solved = _tutor_solved_active(tutor)
    answer_reveal = _approved_tutor_solved_answer(tutor)
    require_guided_evidence_ink = (
        config.guided_evidence_writing_enabled
        and teaching_mode == "GUIDED"
        and bool(current_evidence)
    )
    pattern_matched, pattern_plan = _plan_pattern_add_constant_scene(
        question_id=question_id,
        source_turn_id=source_turn_id,
        tutor_turn_id=tutor_turn_id,
        scene_revision=scene_revision,
        tutor_message_voice=tutor_message_voice,
        tutor=tutor,
        question=question,
        question_anchors=question_anchors,
        student_response=student_response,
        canonical_answer=canonical_answer or "",
        teaching_mode=teaching_mode,
        current_unresolved_component_id=current_unresolved_component_id,
        current_evidence=current_evidence,
        config=config,
    )
    if pattern_matched:
        return pattern_plan
    generic_plan = _plan_confirmed_generic_scene(
        question_id=question_id,
        source_turn_id=source_turn_id,
        tutor_turn_id=tutor_turn_id,
        scene_revision=scene_revision,
        tutor_message_voice=tutor_message_voice,
        tutor=tutor,
        question_anchors=question_anchors,
        canonical_answer=canonical_answer or "",
        teaching_mode=teaching_mode,
        current_evidence=current_evidence,
        config=config,
    )
    if generic_plan is not None:
        return generic_plan
    guided_settings = get_settings().model_copy(
        update={"openai_ai_engine_model": rules.guided_learning.model}
    )
    client = build_openai_ai_engine_client(guided_settings)
    if client is None:
        logger.warning(
            "canvas_teaching_plan_not_generated",
            extra={"question_id": question_id, "reason": "openai_client_unavailable"},
        )
        return None
    try:
        draft = client.plan_canvas_teaching(
            system_prompt=config.system_prompt,
            context={
                "question_id": question_id,
                "question": question,
                "tutor_message_voice": tutor_message_voice,
                "student_response": student_response,
                "teaching_mode": teaching_mode,
                "active_support_level": active_support_level,
                "current_unresolved_component_id": current_unresolved_component_id,
                "allowed_target_ids": allowed_targets,
                "allowed_question_anchors": [
                    {"id": anchor.token_id, "text": anchor.text}
                    for anchor in question_anchors
                ],
                "current_turn_evidence_ids": sorted(current_evidence),
                "require_guided_evidence_ink": require_guided_evidence_ink,
                "direct_explanation_authorized": direct_explanation,
                "direct_explanation_evidence_ref": config.direct_explanation_evidence_ref,
                "direct_explanation_maximum_written_operations": config.direct_explanation_maximum_written_operations,
                "tutor_solved_active": tutor_solved,
                "tutor_solved_answer_authorized": answer_reveal,
                "tutor_solved_actions": [
                    action.model_dump()
                    for action in tutor.tutor_canvas_actions
                    if action.type == "TUTOR_SOLVED_STEP"
                ],
                "maximum_beats": config.maximum_beats,
                "maximum_operations_per_beat": config.maximum_operations_per_beat,
                "rules": {
                    "write_only_confirmed_ideas": True,
                    "support_pane_content_must_not_be_copied": True,
                    "student_write_area_is_forbidden": True,
                    "raw_coordinates_are_forbidden": True,
                },
            },
        )
    except AdapterError as error:
        logger.warning(
            "canvas_teaching_plan_not_generated",
            extra={"question_id": question_id, "reason": error.detail},
        )
        return None

    accepted = _validate_draft(
        draft=draft,
        config=config,
        narration=tutor_message_voice,
        allowed_targets=set(allowed_targets),
        question_anchor_texts=question_anchor_texts,
        current_evidence=current_evidence,
        require_guided_evidence_ink=require_guided_evidence_ink,
        teaching_mode=teaching_mode,
        direct_explanation=direct_explanation,
        tutor_solved=tutor_solved,
        answer_reveal=answer_reveal,
        learner_answer_confirmed=tutor.answer_value_confirmed,
        canonical_answer=canonical_answer or "",
        question=question,
        tutor_solved_step_texts=_current_tutor_solved_step_texts(tutor),
    )
    if accepted is None:
        return None
    return CanvasTeachingPlan(
        plan_id=f"{question_id}:{source_turn_id}:canvas-teaching",
        question_id=question_id,
        source_turn_id=source_turn_id,
        tutor_turn_id=tutor_turn_id,
        scene_revision=scene_revision,
        mode="append",
        teaching_mode=teaching_mode,
        beats=accepted,
    )


def _plan_confirmed_generic_scene(
    question_id: str,
    source_turn_id: str,
    tutor_turn_id: str | None,
    scene_revision: int,
    tutor_message_voice: str,
    tutor: TutorResult,
    question_anchors: list[QuestionTextAnchor],
    canonical_answer: str,
    teaching_mode: CanvasTeachingMode,
    current_evidence: set[str],
    config: CanvasTeachingConfig,
) -> CanvasTeachingPlan | None:
    """Write a grounded, learner-confirmed statement for every question family."""

    if teaching_mode != "GUIDED" or not current_evidence:
        return None
    anchor_by_id = {anchor.token_id: anchor for anchor in question_anchors}
    actions = [
        action
        for action in tutor.tutor_canvas_actions
        if action.target_kind == "QUESTION_ANCHOR"
        and action.target_object_id in anchor_by_id
        and action.confirmed_component_id in current_evidence
    ]
    for action in actions:
        anchor = anchor_by_id[action.target_object_id or ""]
        statement = _spoken_confirmation_statement(
            tutor_message_voice,
            anchor.text,
            canonical_answer,
            tutor.answer_value_confirmed,
        )
        if statement is None:
            continue
        operations = [
            CanvasTeachingOperation(
                operation_id="generic-confirmed-focus",
                kind="HIGHLIGHT",
                target_kind="QUESTION_ANCHOR",
                target_ids=[anchor.token_id],
                zone="QUESTION",
                persistence="PERSIST",
                color_role="NAVY",
            ),
            CanvasTeachingOperation(
                operation_id="generic-confirmed-note",
                kind="WRITE_TEXT",
                target_kind="CANVAS_ZONE",
                target_ids=["ZONE:REASONING"],
                zone="REASONING",
                persistence="PERSIST",
                evidence_ref=action.confirmed_component_id,
                text=statement,
                color_role="NAVY",
                scene_slot=(
                    f"{config.generic_confirmation_scene_slot}:"
                    f"{action.confirmed_component_id}"
                ),
            ),
        ]
        return CanvasTeachingPlan(
            plan_id=f"{question_id}:{source_turn_id}:canvas-teaching",
            question_id=question_id,
            source_turn_id=source_turn_id,
            tutor_turn_id=tutor_turn_id,
            scene_revision=scene_revision,
            mode="append",
            teaching_mode=teaching_mode,
            beats=[
                CanvasTeachingBeat(
                    beat_id="confirmed-generic-scene",
                    sequence=1,
                    speech_anchor=CanvasSpeechAnchor(
                        start_char=0,
                        end_char=len(tutor_message_voice),
                        text=tutor_message_voice,
                    ),
                    operations=operations,
                )
            ],
        )
    return None


def _spoken_confirmation_statement(
    narration: str,
    anchor_text: str,
    canonical_answer: str,
    answer_value_confirmed: bool,
) -> str | None:
    """Keep only a declarative tutor sentence that names the confirmed anchor."""

    for sentence in re.findall(r"[^.!?]+[.!?]?", narration):
        statement = sentence.strip()
        if not statement or statement.endswith("?"):
            continue
        if not _statement_names_anchor(statement, anchor_text):
            continue
        statement = re.sub(
            r"^(?:yes|right|exactly|correct|good)[,!—–\-\s]+",
            "",
            statement,
            flags=re.IGNORECASE,
        )
        if (
            canonical_answer
            and _normalized(canonical_answer) == _normalized(statement)
            and not answer_value_confirmed
        ):
            continue
        return statement
    return None


def _statement_names_anchor(statement: str, anchor_text: str) -> bool:
    normalized_anchor = _normalized(anchor_text)
    if re.fullmatch(r"[A-Za-z0-9]+", normalized_anchor):
        return re.search(
            rf"(?<![A-Za-z0-9]){re.escape(normalized_anchor)}(?![A-Za-z0-9])",
            statement,
            flags=re.IGNORECASE,
        ) is not None
    return normalized_anchor in _normalized(statement)


def _plan_pattern_add_constant_scene(
    question_id: str,
    source_turn_id: str,
    tutor_turn_id: str | None,
    scene_revision: int,
    tutor_message_voice: str,
    tutor: TutorResult,
    question: str,
    question_anchors: list[QuestionTextAnchor],
    student_response: str,
    canonical_answer: str,
    teaching_mode: CanvasTeachingMode,
    current_unresolved_component_id: str | None,
    current_evidence: set[str],
    config: CanvasTeachingConfig,
) -> tuple[bool, CanvasTeachingPlan | None]:
    scene = _pattern_add_constant_scene(
        question=question,
        question_anchors=question_anchors,
        canonical_answer=canonical_answer,
        minimum_cases=config.pattern_add_constant_scene.minimum_cases,
    )
    if not config.pattern_add_constant_scene.enabled or scene is None:
        return False, None
    if teaching_mode == "PARALLEL_EXAMPLE":
        return True, None

    operations: list[CanvasTeachingOperation] = []
    if teaching_mode in config.visual_only_modes:
        operations = _pattern_attention_operations(
            scene=scene,
            unresolved_component_id=current_unresolved_component_id,
        )
    elif teaching_mode == "GUIDED":
        operations = _pattern_guided_operations(
            scene=scene,
            student_response=student_response,
            tutor=tutor,
            current_evidence=current_evidence,
            config=config,
            canonical_answer=canonical_answer,
        )
    elif teaching_mode == "TUTOR_SOLVED":
        operations = _pattern_tutor_solved_operations(
            scene=scene,
            tutor=tutor,
            config=config,
            canonical_answer=canonical_answer,
        )
    else:
        return False, None

    if not operations:
        return True, None
    return True, CanvasTeachingPlan(
        plan_id=f"{question_id}:{source_turn_id}:canvas-teaching",
        question_id=question_id,
        source_turn_id=source_turn_id,
        tutor_turn_id=tutor_turn_id,
        scene_revision=scene_revision,
        mode="append",
        teaching_mode=teaching_mode,
        beats=[
            CanvasTeachingBeat(
                beat_id="pattern-scene",
                sequence=1,
                speech_anchor=CanvasSpeechAnchor(
                    start_char=0,
                    end_char=len(tutor_message_voice),
                    text=tutor_message_voice,
                ),
                operations=operations,
            )
        ],
    )


def _pattern_add_constant_scene(
    question: str,
    question_anchors: list[QuestionTextAnchor],
    canonical_answer: str,
    minimum_cases: int,
) -> PatternAddConstantScene | None:
    canonical = _CANONICAL_PATTERN_RE.fullmatch(canonical_answer.strip())
    if canonical is None:
        return None
    variable, canonical_operator, canonical_fixed = canonical.groups()
    cases = list(_PATTERN_CASE_RE.finditer(question))
    if len(cases) < minimum_cases:
        return None
    if any(
        match.group("operator") != canonical_operator
        or match.group("fixed") != canonical_fixed
        for match in cases
    ):
        return None

    by_span = {
        (anchor.char_start, anchor.char_end): anchor.token_id
        for anchor in question_anchors
    }
    changing_ids = [
        by_span.get((match.start("starting"), match.end("starting")))
        for match in cases
    ]
    fixed_ids = [
        by_span.get((match.start("fixed"), match.end("fixed")))
        for match in cases
    ]
    operator_ids = [
        by_span.get((match.start("operator"), match.end("operator")))
        for match in cases
    ]
    if any(token_id is None for token_id in [*changing_ids, *fixed_ids, *operator_ids]):
        return None
    return {
        "variable": variable,
        "operator": canonical_operator,
        "fixed_value": canonical_fixed,
        "changing_ids": [token_id for token_id in changing_ids if token_id is not None],
        "fixed_ids": [token_id for token_id in fixed_ids if token_id is not None],
        "operator_ids": [token_id for token_id in operator_ids if token_id is not None],
    }


def _pattern_attention_operations(
    scene: PatternAddConstantScene,
    unresolved_component_id: str | None,
) -> list[CanvasTeachingOperation]:
    if unresolved_component_id == "CHANGING_VALUE":
        return _question_marks(
            operation_id="focus-changing-values",
            kind="CIRCLE",
            target_ids=scene["changing_ids"],
            color_role="AMBER",
            persistence="PULSE",
        )
    if unresolved_component_id in {"FIXED_VALUE", "OPERATION"}:
        return _question_marks(
            operation_id="focus-fixed-terms",
            kind="HIGHLIGHT",
            target_ids=[*scene["operator_ids"], *scene["fixed_ids"]],
            color_role="TEAL",
            persistence="PULSE",
        )
    return []


def _pattern_guided_operations(
    scene: PatternAddConstantScene,
    student_response: str,
    tutor: TutorResult,
    current_evidence: set[str],
    config: CanvasTeachingConfig,
    canonical_answer: str,
) -> list[CanvasTeachingOperation]:
    state = tutor.guided_teaching_state
    confirmed = set(state.confirmed_component_ids) if state is not None else set()
    pattern_config = config.pattern_add_constant_scene
    if tutor.answer_value_confirmed or _normalized(student_response) == _normalized(canonical_answer):
        return [
            _pattern_write(
                operation_id="write-final-rule",
                kind="WRITE_MATH",
                content=canonical_answer,
                evidence_ref="GENERAL_RULE",
                scene_slot="rule_conclusion",
            )
        ]
    if "CHANGING_VALUE" in current_evidence:
        if _student_names_variable(student_response, scene["variable"]):
            return [
                _pattern_write(
                    operation_id="write-variable-meaning",
                    kind="WRITE_TEXT",
                    content=pattern_config.variable_note.format(variable=scene["variable"]),
                    evidence_ref="CHANGING_VALUE",
                    scene_slot="variable_conclusion",
                )
            ]
        return [
            *_question_marks(
                operation_id="circle-changing-values",
                kind="CIRCLE",
                target_ids=scene["changing_ids"],
                color_role="AMBER",
                persistence="PERSIST",
            ),
            _pattern_write(
                operation_id="write-changing-conclusion",
                kind="WRITE_TEXT",
                content=pattern_config.changing_note,
                evidence_ref="CHANGING_VALUE",
                scene_slot="changing_conclusion",
            ),
        ]
    if "FIXED_VALUE" in current_evidence:
        complete_term = _student_names_complete_fixed_term(student_response, scene)
        fixed_marks = _question_marks(
            operation_id="highlight-fixed-terms",
            kind="HIGHLIGHT",
            target_ids=[*scene["operator_ids"], *scene["fixed_ids"]],
            color_role="TEAL",
            persistence="PERSIST" if complete_term else "PULSE",
        )
        if not complete_term:
            return fixed_marks
        return [
            *fixed_marks,
            CanvasTeachingOperation(
                operation_id="connect-fixed-values",
                kind="CONNECT",
                target_kind="QUESTION_ANCHOR",
                target_ids=scene["fixed_ids"],
                zone="QUESTION",
                persistence="PERSIST",
                color_role="TEAL",
            ),
            _pattern_write(
                operation_id="write-fixed-conclusion",
                kind="WRITE_TEXT",
                content=pattern_config.fixed_note.format(
                    operator=scene["operator"], fixed_value=scene["fixed_value"]
                ),
                evidence_ref="FIXED_VALUE",
                scene_slot="fixed_conclusion",
            ),
        ]
    if "OPERATION" in current_evidence and {"CHANGING_VALUE", "FIXED_VALUE"}.issubset(confirmed):
        return [
            CanvasTeachingOperation(
                operation_id="connect-changing-values",
                kind="CONNECT",
                target_kind="QUESTION_ANCHOR",
                target_ids=scene["changing_ids"],
                zone="QUESTION",
                persistence="PERSIST",
                color_role="AMBER",
            ),
            _pattern_write(
                operation_id="write-pattern-structure",
                kind="WRITE_TEXT",
                content=pattern_config.structure_note.format(
                    operator=scene["operator"], fixed_value=scene["fixed_value"]
                ),
                evidence_ref="OPERATION",
                scene_slot="operation_conclusion",
            ),
        ]
    return []


def _pattern_tutor_solved_operations(
    scene: PatternAddConstantScene,
    tutor: TutorResult,
    config: CanvasTeachingConfig,
    canonical_answer: str,
) -> list[CanvasTeachingOperation]:
    action = next(
        (
            item
            for item in tutor.tutor_canvas_actions
            if item.type == "TUTOR_SOLVED_STEP"
        ),
        None,
    )
    if action is None or action.step_index is None:
        return []
    pattern_config = config.pattern_add_constant_scene
    if action.answer_reveal_allowed:
        return [
            _pattern_write(
                operation_id="tutor-solved-final-rule",
                kind="WRITE_MATH",
                content=canonical_answer,
                evidence_ref="GENERAL_RULE",
                scene_slot="rule_conclusion",
            )
        ]
    if action.step_index == 1:
        return [
            *_question_marks(
                operation_id="tutor-solved-circle-changing-values",
                kind="CIRCLE",
                target_ids=scene["changing_ids"],
                color_role="AMBER",
                persistence="PERSIST",
            ),
            _pattern_write(
                operation_id="tutor-solved-changing-conclusion",
                kind="WRITE_TEXT",
                content=pattern_config.changing_note,
                evidence_ref="CHANGING_VALUE",
                scene_slot="changing_conclusion",
            ),
        ]
    if action.step_index == 2:
        return [
            *_question_marks(
                operation_id="tutor-solved-highlight-fixed-terms",
                kind="HIGHLIGHT",
                target_ids=[*scene["operator_ids"], *scene["fixed_ids"]],
                color_role="TEAL",
                persistence="PERSIST",
            ),
            CanvasTeachingOperation(
                operation_id="tutor-solved-connect-fixed-values",
                kind="CONNECT",
                target_kind="QUESTION_ANCHOR",
                target_ids=scene["fixed_ids"],
                zone="QUESTION",
                persistence="PERSIST",
                color_role="TEAL",
            ),
            _pattern_write(
                operation_id="tutor-solved-fixed-conclusion",
                kind="WRITE_TEXT",
                content=pattern_config.fixed_note.format(
                    operator=scene["operator"], fixed_value=scene["fixed_value"]
                ),
                evidence_ref="FIXED_VALUE",
                scene_slot="fixed_conclusion",
            ),
        ]
    if action.step_index == 3:
        return [
            CanvasTeachingOperation(
                operation_id="tutor-solved-connect-changing-values",
                kind="CONNECT",
                target_kind="QUESTION_ANCHOR",
                target_ids=scene["changing_ids"],
                zone="QUESTION",
                persistence="PERSIST",
                color_role="AMBER",
            ),
            _pattern_write(
                operation_id="tutor-solved-pattern-structure",
                kind="WRITE_TEXT",
                content=pattern_config.structure_note.format(
                    operator=scene["operator"], fixed_value=scene["fixed_value"]
                ),
                evidence_ref="OPERATION",
                scene_slot="operation_conclusion",
            ),
        ]
    return [
        _pattern_write(
            operation_id="tutor-solved-variable-meaning",
            kind="WRITE_TEXT",
            content=pattern_config.variable_note.format(variable=scene["variable"]),
            evidence_ref="CHANGING_VALUE",
            scene_slot="variable_conclusion",
        )
    ]


def _question_marks(
    operation_id: str,
    kind: Literal["CIRCLE", "HIGHLIGHT"],
    target_ids: list[str],
    color_role: Literal["AMBER", "TEAL"],
    persistence: Literal["PULSE", "PERSIST"],
) -> list[CanvasTeachingOperation]:
    return [
        CanvasTeachingOperation(
            operation_id=f"{operation_id}-{index}",
            kind=kind,
            target_kind="QUESTION_ANCHOR",
            target_ids=target_ids[index:index + 4],
            zone="QUESTION",
            persistence=persistence,
            color_role=color_role,
        )
        for index in range(0, len(target_ids), 4)
    ]


def _pattern_write(
    operation_id: str,
    kind: Literal["WRITE_TEXT", "WRITE_MATH"],
    content: str,
    evidence_ref: str,
    scene_slot: str,
) -> CanvasTeachingOperation:
    return CanvasTeachingOperation(
        operation_id=operation_id,
        kind=kind,
        target_kind="CANVAS_ZONE",
        target_ids=["ZONE:REASONING"],
        zone="REASONING",
        persistence="PERSIST",
        evidence_ref=evidence_ref,
        text=content if kind == "WRITE_TEXT" else None,
        latex=content if kind == "WRITE_MATH" else None,
        color_role="NAVY",
        scene_slot=scene_slot,
    )


def _student_names_complete_fixed_term(
    student_response: str,
    scene: PatternAddConstantScene,
) -> bool:
    normalized = student_response.casefold().replace("−", "-")
    if scene["operator"] == "+":
        return bool(re.search(rf"(?:\+|plus)\s*{re.escape(scene['fixed_value'])}\b", normalized))
    if scene["operator"] in {"×", "*"}:
        return bool(re.search(rf"(?:×|\*|times)\s*{re.escape(scene['fixed_value'])}\b", normalized))
    return bool(re.search(rf"(?:-|minus)\s*{re.escape(scene['fixed_value'])}\b", normalized))


def _student_names_variable(student_response: str, variable: str) -> bool:
    return bool(re.fullmatch(rf"\s*(?:it(?:'s| is)\s*)?{re.escape(variable)}\s*[.!]?\s*", student_response, re.IGNORECASE))


def _current_turn_evidence(tutor: TutorResult) -> set[str]:
    state = tutor.guided_teaching_state
    if state is None:
        return set()
    return {
        claim.concept_id
        for claim in state.last_turn_evidence
        if claim.status == "DEMONSTRATED"
    }


def _approved_direct_explanation(tutor: TutorResult, config: CanvasTeachingConfig) -> bool:
    contribution = tutor.contribution
    return (
        config.direct_explanation_enabled
        and contribution is not None
        and contribution.kind == "EXPLANATION_REQUEST"
        and contribution.explained_idea is not None
        and contribution.explained_idea.strip() != ""
    )


def _tutor_solved_active(tutor: TutorResult) -> bool:
    return any(action.type == "TUTOR_SOLVED_STEP" for action in tutor.tutor_canvas_actions)


def _approved_tutor_solved_answer(tutor: TutorResult) -> bool:
    return any(
        action.type == "TUTOR_SOLVED_STEP" and action.answer_reveal_allowed
        for action in tutor.tutor_canvas_actions
    )


def _current_tutor_solved_step_texts(tutor: TutorResult) -> list[str]:
    return [
        action.text
        for action in tutor.tutor_canvas_actions
        if action.type == "TUTOR_SOLVED_STEP" and action.text is not None
    ]


def _validate_draft(
    draft: CanvasTeachingPlanDraft,
    config: CanvasTeachingConfig,
    narration: str,
    allowed_targets: set[str],
    question_anchor_texts: dict[str, str],
    current_evidence: set[str],
    require_guided_evidence_ink: bool,
    teaching_mode: CanvasTeachingMode,
    direct_explanation: bool,
    tutor_solved: bool,
    answer_reveal: bool,
    learner_answer_confirmed: bool,
    canonical_answer: str,
    question: str,
    tutor_solved_step_texts: list[str],
) -> list[CanvasTeachingBeat] | None:
    if len(draft.beats) > config.maximum_beats:
        return None
    direct_explanation_writes = 0
    guided_evidence_writes = 0
    accepted: list[CanvasTeachingBeat] = []
    for beat in draft.beats:
        if len(beat.operations) > config.maximum_operations_per_beat:
            return None
        anchor = synchronize_speech_anchor(beat.speech_anchor, narration)
        if anchor is None:
            return None
        operations = [
            _with_scene_slot(operation, config)
            for operation in beat.operations
            if _operation_is_authorized(
                operation=operation,
                allowed_targets=allowed_targets,
                question_anchor_texts=question_anchor_texts,
                current_evidence=current_evidence,
                learner_answer_confirmed=learner_answer_confirmed,
                teaching_mode=teaching_mode,
                direct_explanation=direct_explanation,
                tutor_solved=tutor_solved,
                answer_reveal=answer_reveal,
                canonical_answer=canonical_answer,
                narration=narration,
                question=question,
                tutor_solved_step_texts=tutor_solved_step_texts,
                config=config,
            )
        ]
        if len(operations) != len(beat.operations):
            return None
        direct_explanation_writes += sum(
            operation.kind in {"WRITE_TEXT", "WRITE_MATH"}
            for operation in operations
        )
        if teaching_mode == "GUIDED":
            guided_evidence_writes += sum(
                operation.kind in {"WRITE_TEXT", "WRITE_MATH"}
                for operation in operations
            )
        if direct_explanation and direct_explanation_writes > config.direct_explanation_maximum_written_operations:
            return None
        accepted.append(
            beat.model_copy(
                update={"speech_anchor": anchor, "operations": operations}
            )
        )
    if require_guided_evidence_ink and guided_evidence_writes == 0:
        return None
    if guided_evidence_writes > config.guided_evidence_maximum_written_operations:
        return None
    return accepted


def _with_scene_slot(
    operation: CanvasTeachingOperation,
    config: CanvasTeachingConfig,
) -> CanvasTeachingOperation:
    """Attach a configured visual slot to an approved learner-confirmed note."""

    if operation.kind not in {"WRITE_TEXT", "WRITE_MATH"}:
        return operation.model_copy(update={"scene_slot": None})
    if operation.evidence_ref is None:
        return operation.model_copy(update={"scene_slot": None})
    return operation.model_copy(
        update={
            "scene_slot": config.guided_evidence_scene_slots.get(
                operation.evidence_ref
            )
        }
    )


def _operation_is_authorized(
    operation: CanvasTeachingOperation,
    allowed_targets: set[str],
    question_anchor_texts: dict[str, str],
    current_evidence: set[str],
    learner_answer_confirmed: bool,
    teaching_mode: CanvasTeachingMode,
    direct_explanation: bool,
    tutor_solved: bool,
    answer_reveal: bool,
    canonical_answer: str,
    narration: str,
    question: str,
    tutor_solved_step_texts: list[str],
    config: CanvasTeachingConfig,
) -> bool:
    if not set(operation.target_ids).issubset(allowed_targets):
        return False
    if operation.kind == "CONNECT":
        return False
    if operation.target_kind == "QUESTION_ANCHOR" and not all(
        _is_math_bearing_question_token(question_anchor_texts.get(target_id, ""))
        for target_id in operation.target_ids
    ):
        return False
    if operation.zone == "QUESTION" and operation.kind in {"WRITE_TEXT", "WRITE_MATH"}:
        return False
    if operation.kind not in {"WRITE_TEXT", "WRITE_MATH"}:
        return operation.evidence_ref is None
    if teaching_mode in config.visual_only_modes:
        return False
    content = operation.latex or operation.text or ""
    if (
        canonical_answer
        and _normalized(content) == _normalized(canonical_answer)
        and not answer_reveal
        and not learner_answer_confirmed
    ):
        return False
    if operation.target_kind != "CANVAS_ZONE" or operation.target_ids != [f"ZONE:{operation.zone}"]:
        return False
    if direct_explanation:
        return (
            operation.evidence_ref == config.direct_explanation_evidence_ref
            and operation.zone == "REASONING"
            and _content_terms_are_spoken(content, narration)
            and _numeric_terms_come_from_question(content, question)
        )
    if tutor_solved:
        return (
            config.tutor_solved_writing_enabled
            and _content_terms_are_spoken(content, narration)
            and _content_terms_are_spoken(content, " ".join(tutor_solved_step_texts))
        )
    if teaching_mode == "GUIDED":
        return (
            operation.evidence_ref in current_evidence
            and operation.zone == "REASONING"
            and operation.persistence == "PERSIST"
            and operation.color_role == "NAVY"
            and _content_terms_are_spoken(content, narration)
        )
    if operation.evidence_ref not in current_evidence:
        return False
    return operation.zone in {"REASONING", "TUTOR_SOLUTION"}


def _is_math_bearing_question_token(token: str) -> bool:
    normalized = token.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        return True
    if re.fullmatch(r"[A-Za-z]", normalized):
        return True
    if re.fullmatch(r"[b-df-hj-np-tv-z]{2,}", normalized.casefold()):
        return True
    return normalized in {"+", "−", "-", "×", "/", "=", "(", ")"}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("−", "-")


def _content_terms_are_spoken(content: str, narration: str) -> bool:
    without_latex_commands = re.sub(r"\\[A-Za-z]+", " ", content)
    content_terms = set(re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?", without_latex_commands.casefold()))
    narration_terms = set(re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?", narration.casefold()))
    return bool(content_terms) and content_terms.issubset(narration_terms)


def _numeric_terms_come_from_question(content: str, question: str) -> bool:
    content_numbers = set(re.findall(r"\d+(?:\.\d+)?", content))
    question_numbers = set(re.findall(r"\d+(?:\.\d+)?", question))
    return content_numbers.issubset(question_numbers)


def synchronize_speech_anchor(
    anchor: CanvasSpeechAnchor,
    narration: str,
) -> CanvasSpeechAnchor | None:
    first_match = narration.find(anchor.text)
    if first_match < 0:
        return None
    second_match = narration.find(anchor.text, first_match + 1)
    if second_match >= 0:
        if narration[anchor.start_char:anchor.end_char] != anchor.text:
            return None
        return anchor
    return anchor.model_copy(
        update={
            "start_char": first_match,
            "end_char": first_match + len(anchor.text),
        }
    )


def _teaching_mode(
    tutor: TutorResult,
    active_support_level: str | None,
    config: CanvasTeachingConfig,
) -> CanvasTeachingMode:
    if _tutor_solved_active(tutor):
        return "TUTOR_SOLVED"
    if any(action.type == "SHOW_PARALLEL" for action in tutor.tutor_canvas_actions):
        return "PARALLEL_EXAMPLE"
    if _approved_direct_explanation(tutor, config):
        return "DIRECT_EXPLANATION"
    if active_support_level in {"HINT", "VISUAL_CUE", "SCAFFOLD"}:
        return active_support_level
    if any(action.type == "SHOW_CUE" for action in tutor.tutor_canvas_actions):
        return "VISUAL_CUE"
    if any(action.type == "OPEN_SCAFFOLD_STEP" for action in tutor.tutor_canvas_actions):
        return "SCAFFOLD"
    if tutor.hint_level > 0:
        return "HINT"
    return "GUIDED"
