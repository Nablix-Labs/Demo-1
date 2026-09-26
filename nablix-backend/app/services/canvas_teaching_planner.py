from __future__ import annotations

import re

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
            operation
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
