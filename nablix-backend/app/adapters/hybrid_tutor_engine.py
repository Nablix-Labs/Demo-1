"""Hybrid Tutor Engine adapter.

Wires Sanya's Hybrid Tutor Engine (pure functions in `app.ai_engine.classifier`,
contracts in `app.models.guided_learning`) into the same seam the legacy
`TutorEngineServiceAdapter` (`app/adapters/tutor_engine.py`) already satisfies.
Callers outside this file never see a Hybrid-specific type — everything in and
out is `AdapterContext` / `RAGResult` / `StudentModelResult` / `TutorResult`,
exactly like the legacy adapter.
"""

from app.ai_engine.classifier import (
    build_openai_ai_engine_client,
    decide_hybrid_pedagogy,
    hybrid_phase2_system_prompt,
    plan_hybrid_canvas_pedagogy,
    resolve_hybrid_student_evidence,
    validate_hybrid_canvas_action_reveal_policy,
    validate_hybrid_tutor_turn,
    validate_hybrid_tutor_wording,
)
from app.ai_engine.classifier_config import ClassifierRulesConfig, load_classifier_rules
from app.core.config import get_settings
from app.core.exceptions import AdapterError
from app.models.adapters import AdapterContext, RAGResult, StudentModelResult, TutorResult
from app.models.canvas_memory import CanvasEvent
from app.models.guided_learning import (
    HybridCanvasPlannerRequest,
    HybridEvidenceSource,
    HybridInputReliability,
    HybridPedagogicalState,
    HybridPedagogyDecision,
    HybridStudentEvidence,
    HybridSupportState,
    HybridTutorRequest,
    HybridTutorTurnContext,
    OrderedCanvasMemoryItem,
)

_HYBRID_SCHEMA_VERSION = "1.0"

# Legacy AdapterContext.input_source values ("TEXT"/"VOICE"/"CANVAS"/"CHOICE",
# see app/adapters/tutor_engine.py:_coerce_input_source) map onto Hybrid's
# HybridEvidenceSource one-for-one except CHOICE, which is a structured
# selection rather than free text.
_INPUT_SOURCE_MAP: dict[str, HybridEvidenceSource] = {
    "TEXT": "TEXT",
    "VOICE": "VOICE",
    "CANVAS": "CANVAS",
    "CHOICE": "STRUCTURED",
}


def _ordered_canvas_memory_from_events(
    events: list[CanvasEvent],
    ocr_confidence: float | None,
    minimum_ocr_confidence: float,
) -> list[OrderedCanvasMemoryItem]:
    """Map existing canvas memory onto Hybrid's `OrderedCanvasMemoryItem` shape.

    `CanvasEvent` already carries every field `OrderedCanvasMemoryItem` needs
    except `object_id` and `reliability`, so this is a near-mechanical
    conversion rather than a new memory model.

    Events with no `turn_id`/`question_id` are dropped — both are required
    (non-empty) on `OrderedCanvasMemoryItem` and a memory item that isn't tied
    to a turn and question can't be a valid Hybrid tutor anchor.

    Reliability is per-turn OCR confidence, not per-object: this backend has
    no per-object confidence today, only one OCR confidence per canvas
    submission (`AdapterContext.ocr_confidence`), matching
    `HybridStudentEvidence.ocr_confidence`'s shape. Tutor/support-authored
    events are always reliable — they were not read off the student's
    handwriting, the backend produced them itself.
    """

    items: list[OrderedCanvasMemoryItem] = []
    for event in events:
        if not event.turn_id or not event.question_id:
            continue
        reliability: HybridInputReliability = (
            "RELIABLE"
            if event.actor != "STUDENT"
            or (ocr_confidence is not None and ocr_confidence >= minimum_ocr_confidence)
            else "NEEDS_WRITING"
        )
        items.append(
            OrderedCanvasMemoryItem(
                object_id=event.target_object_id or f"{event.turn_id}:{event.order_index}",
                order_index=event.order_index,
                turn_id=event.turn_id,
                question_id=event.question_id,
                actor=event.actor,
                action_type=event.action_type,
                content=event.content,
                math_text=event.math_text,
                target_object_id=event.target_object_id,
                semantic_tag=event.semantic_tag,
                source_id=event.source_id,
                active_state=event.active_state,
                reliability=reliability,
            )
        )
    return items


def _default_hybrid_support_state() -> HybridSupportState:
    return HybridSupportState(
        current_support="NONE",
        highest_support_used="NONE",
        active_support_id=None,
        support_history_ids=[],
        consecutive_stuck_count=0,
    )


def _default_hybrid_pedagogical_state() -> HybridPedagogicalState:
    # STUCK is the same "no evidence evaluated yet" default Sanya's own tests
    # use for a fresh question (see tests/test_ai_engine.py) — completed
    # component IDs stay empty either way, so this only affects the label the
    # LLM sees on the very first turn of a question, not any protection.
    return HybridPedagogicalState(
        student_state="STUCK",
        completed_component_ids=[],
        current_answer_step_index=0,
        consecutive_stuck_count=0,
    )


def build_hybrid_tutor_request(
    context: AdapterContext,
    rules: ClassifierRulesConfig,
) -> HybridTutorRequest:
    """Build the "one temporary Hybrid request per turn" from existing state only.

    Every field is read from `context` — nothing here is client-controlled in
    a way that could reach a backend-owned decision (e.g. `approved_answer_reveal`,
    which does not appear on this request at all; it is decided later, inside
    the adapter, from server-side state only).

    Takes only `context`, not a `SessionRecord`, on purpose: the caller
    (interaction_service.py/canvas_service.py) already folds session state
    onto `AdapterContext` before calling any tutor adapter — `guided_teaching_state`
    does this for the legacy path today, `hybrid_pedagogical_state` /
    `hybrid_support_state` / `canvas_events` do it here. An adapter reaching
    back into session storage itself would invert the existing
    services-call-adapters layering.

    Raises `ValueError` if the question doesn't carry what Hybrid requires
    (a `question_type`/`answer_spec` with authored `answer_steps`) — the
    caller is responsible for falling back to the legacy adapter when that
    happens, not this function.
    """

    if context.question_id is None or context.question is None:
        raise ValueError("Hybrid tutor request requires a question_id and question text.")
    if context.question_type is None:
        raise ValueError("Hybrid tutor request requires a question_type.")
    if context.answer_spec is None:
        raise ValueError("Hybrid tutor request requires an answer_spec.")

    canvas_events = context.canvas_events
    ordered_canvas_memory = _ordered_canvas_memory_from_events(
        canvas_events,
        context.ocr_confidence,
        rules.guided_learning.minimum_ocr_confidence,
    )

    student_evidence = HybridStudentEvidence(
        input_source=_INPUT_SOURCE_MAP.get(context.input_source or "TEXT", "TEXT"),
        raw_voice_transcript=context.raw_voice_transcript,
        transcript_confidence=context.transcript_confidence,
        transcript_alternatives=context.transcript_alternatives,
        typed_answer=context.message if context.input_source == "TEXT" else None,
        structured_answer=context.structured_answer,
        selected_option_id=context.selected_option_id,
        selected_option_text=context.selected_option_text,
        raw_ocr_text=None,
        processed_math_text=context.detected_equation,
        ocr_confidence=context.ocr_confidence,
        canvas_object_ids=[
            event.target_object_id
            for event in canvas_events
            if event.actor == "STUDENT" and event.target_object_id
        ],
    )

    return HybridTutorRequest(
        schema_version=_HYBRID_SCHEMA_VERSION,
        question_id=context.question_id,
        question_type=context.question_type,
        question=context.question,
        answer_spec=context.answer_spec,
        support_state=context.hybrid_support_state or _default_hybrid_support_state(),
        session_history=context.conversation_history,
        ordered_canvas_memory=ordered_canvas_memory,
        student_evidence=student_evidence,
        pedagogical_state=(
            context.hybrid_pedagogical_state or _default_hybrid_pedagogical_state()
        ),
    )


class HybridTutorEngineAdapter:
    """Satisfies the same seam as `TutorEngineServiceAdapter`
    (`app/adapters/tutor_engine.py`) — `evaluate(context, rag, student) ->
    TutorResult` — so callers never need to know which engine produced a
    given turn.

    ponytail: `authored_support_content` and `confirmed_tutor_anchors` are
    always empty here — this backend has no per-support-type retrieval yet
    (RAG today fetches one document per legacy hint level, not one per rung
    of Hybrid's 6-rung support ladder). `decide_hybrid_pedagogy` degrades
    gracefully when given no candidates (falls back to LOAD_REDUCTION instead
    of SUPPORT_ESCALATION), so this is a real but bounded gap, not silent
    wrongness. Upgrade when Aditya's RAG layer exposes per-support-type
    content lookup.
    """

    async def evaluate(
        self,
        context: AdapterContext,
        rag: RAGResult,
        student: StudentModelResult,
    ) -> TutorResult:
        rules = load_classifier_rules()
        request = build_hybrid_tutor_request(context, rules)
        resolution = resolve_hybrid_student_evidence(
            request.student_evidence,
            request.question,
            rules.guided_learning.minimum_voice_transcript_confidence,
            rules.guided_learning.minimum_ocr_confidence,
        )

        if resolution.input_reliability == "NEEDS_WRITING":
            return self._write_instruction_result(context, request)

        decision = decide_hybrid_pedagogy(
            request.pedagogical_state,
            request.support_state,
            authored_support_content=[],
            rules=rules,
        )
        approved_answer_reveal = decision.support_action == "TUTOR_SOLVED"

        settings = get_settings()
        openai_client = build_openai_ai_engine_client(settings)
        if openai_client is None:
            raise AdapterError(
                "hybrid_tutor_engine",
                "Hybrid orchestration requires NABLIX_USE_OPENAI_AI_ENGINE=true.",
            )

        turn_context = HybridTutorTurnContext(
            request=request,
            resolved_student_meaning=resolution.resolved_student_meaning,
            input_reliability=resolution.input_reliability,
            decision=decision,
            canvas_actions=[],
            active_support_content=None,
            approved_answer_reveal=approved_answer_reveal,
        )
        system_prompt = (
            f"{hybrid_phase2_system_prompt('SEMANTIC', rules)}\n\n"
            f"{rules.guided_learning.hybrid_prompts.wording_prompt}"
        )
        turn = openai_client.generate_hybrid_tutor_turn(turn_context, system_prompt)
        validated_turn = validate_hybrid_tutor_turn(request, resolution, turn)

        planner_request = HybridCanvasPlannerRequest(
            turn_id=context.source_turn_id or "UNKNOWN",
            question_id=request.question_id,
            answer_spec=request.answer_spec,
            current_answer_step_index=validated_turn.current_answer_step_index,
            current_answer_step_id=validated_turn.current_answer_step_id,
            completed_component_ids=validated_turn.completed_components,
            input_reliability=resolution.input_reliability,
            decision=decision,
            ordered_canvas_memory=request.ordered_canvas_memory,
            authored_support_content=[],
            confirmed_tutor_anchors=[],
            approved_answer_reveal=approved_answer_reveal,
            active_action_ids=[],
        )
        canvas_actions = plan_hybrid_canvas_pedagogy(planner_request, rules)
        for action in canvas_actions:
            validate_hybrid_canvas_action_reveal_policy(
                action, decision.support_action, approved_answer_reveal
            )
        tutor_voice_text = validate_hybrid_tutor_wording(
            validated_turn.tutor_voice_text,
            canvas_actions,
            request.answer_spec.canonical_answer,
            rules,
        )

        question_completed = validated_turn.current_answer_step_index is None

        return TutorResult(
            evaluation=validated_turn.pedagogical_state,
            error_type="UNKNOWN_ERROR" if validated_turn.pedagogical_state == "WRONG" else "NONE",
            intent="SUBMITTING_ANSWER",
            response_strategy=decision.strategy,
            tutor_message=tutor_voice_text,
            tutor_message_voice=tutor_voice_text,
            voice_optimised=True,
            hint_level=0,
            answer_reveal_allowed=approved_answer_reveal,
            confidence=1.0,
            input_source=context.input_source or "TEXT",
            transcript_confidence=context.transcript_confidence,
            attempt_increment=0,
            recommended_conversation_action=(
                "ADVANCE_TO_NEXT_QUESTION" if question_completed else "ACKNOWLEDGE_ANSWER"
            ),
            question_completed=question_completed,
            answer_value_confirmed=question_completed,
            hybrid_turn=validated_turn,
            hybrid_evidence_resolution=resolution,
            hybrid_decision=decision,
            hybrid_canvas_memory=request.ordered_canvas_memory,
        )

    def _write_instruction_result(
        self, context: AdapterContext, request: HybridTutorRequest
    ) -> TutorResult:
        """The reliability gate rejected this turn's evidence before the one
        OpenAI call — the handoff requires zero attempts/events/progression/
        support here, so no engine call happens at all.
        """

        message = "Please write out that step so I can check it."
        return TutorResult(
            evaluation="NEEDS_WRITING",
            error_type="NONE",
            intent="SUBMITTING_ANSWER",
            response_strategy="LOAD_REDUCTION",
            tutor_message=message,
            tutor_message_voice=message,
            voice_optimised=True,
            hint_level=0,
            answer_reveal_allowed=False,
            confidence=1.0,
            input_source=context.input_source or "TEXT",
            transcript_confidence=context.transcript_confidence,
            attempt_increment=0,
            recommended_conversation_action="WAIT_FOR_STUDENT",
            question_completed=False,
            requires_written_math_evidence=True,
        )
