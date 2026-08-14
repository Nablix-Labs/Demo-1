from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.models.student_model_session import AnswerSpec, QuestionType, SupportUsed


GuidedStudentState = Literal["CORRECT", "PARTIAL", "WRONG", "STUCK", "UNCLEAR"]
HybridPedagogicalStateName = Literal[
    "CORRECT",
    "PARTIAL",
    "WRONG",
    "STUCK",
    "NEEDS_WRITING",
]
HybridInputReliability = Literal["RELIABLE", "NEEDS_WRITING"]
HybridEvidenceResolutionSource = Literal[
    "TYPED",
    "STRUCTURED",
    "OCR",
    "VOICE_CONTEXT",
    "NEEDS_WRITING",
]
HybridExpectedInput = Literal[
    "VOICE",
    "WRITE",
    "STRUCTURED",
    "VOICE_OR_WRITE",
    "NONE",
]
HybridEvidenceSource = Literal[
    "VOICE",
    "TEXT",
    "STRUCTURED",
    "CANVAS",
    "MULTIMODAL",
]
CanvasMemoryActor = Literal["STUDENT", "TUTOR", "SYSTEM_SUPPORT"]
CanvasMemoryState = Literal["ACTIVE", "SUPERSEDED", "CLEARED"]
CanvasActionType = Literal[
    "HIGHLIGHT",
    "CIRCLE",
    "GROUP",
    "ARROW",
    "INSERT_MATH",
    "INSERT_LABEL",
    "SHOW_CUE",
    "OPEN_SCAFFOLD_STEP",
    "SHOW_PARALLEL",
    "TUTOR_SOLVED_STEP",
    "FOCUS",
]
CanvasActionLayer = Literal["TUTOR", "SUPPORT"]
HybridPedagogyStrategy = Literal[
    "ADVANCE_AND_FADE",
    "AFFIRM_AND_ISOLATE",
    "SOCRATIC_MISCONCEPTION_TEST",
    "LOAD_REDUCTION",
    "SUPPORT_ESCALATION",
]
CanvasSemanticTag = Literal[
    "changing_value",
    "fixed_value",
    "operation",
    "student_attempt",
    "misconception_test",
    "answer_step",
]


class GuidedLearningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class HybridStudentEvidence(GuidedLearningModel):
    input_source: HybridEvidenceSource
    raw_voice_transcript: str | None
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    transcript_alternatives: list[str]
    typed_answer: str | None
    structured_answer: dict[str, str]
    selected_option_id: str | None
    selected_option_text: str | None
    raw_ocr_text: str | None
    processed_math_text: str | None
    ocr_confidence: float | None = Field(ge=0.0, le=1.0)
    canvas_object_ids: list[str]


class HybridEvidenceResolution(GuidedLearningModel):
    input_reliability: HybridInputReliability
    resolved_student_meaning: str | None
    resolution_source: HybridEvidenceResolutionSource
    can_update_learning_state: StrictBool


class AuthoredAnswerStep(GuidedLearningModel):
    step_id: str = Field(min_length=1)
    order_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    component_id: str = Field(min_length=1)


class OrderedCanvasMemoryItem(GuidedLearningModel):
    object_id: str = Field(min_length=1)
    order_index: int = Field(ge=0)
    turn_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    actor: CanvasMemoryActor
    action_type: str = Field(min_length=1)
    content: str | None
    math_text: str | None
    target_object_id: str | None
    semantic_tag: str | None
    source_id: str | None
    active_state: CanvasMemoryState
    reliability: HybridInputReliability


class HybridSupportState(GuidedLearningModel):
    current_support: SupportUsed
    highest_support_used: SupportUsed
    active_support_id: str | None
    support_history_ids: list[str]
    consecutive_stuck_count: int = Field(ge=0)


class HybridPedagogicalState(GuidedLearningModel):
    student_state: HybridPedagogicalStateName
    completed_component_ids: list[str]
    current_answer_step_index: int | None = Field(ge=0)
    consecutive_stuck_count: int = Field(ge=0)


class HybridPedagogyDecision(GuidedLearningModel):
    strategy: HybridPedagogyStrategy
    support_action: SupportUsed
    support_id: str | None
    next_expected_input: HybridExpectedInput


class HybridAuthoredSupportContent(GuidedLearningModel):
    source_id: str = Field(min_length=1)
    support_action: SupportUsed
    text: str = Field(min_length=1)


class HybridCanvasPlannerRequest(GuidedLearningModel):
    turn_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    answer_spec: AnswerSpec
    component_ids: list[str]
    current_answer_step_index: int | None = Field(ge=0)
    current_answer_step_id: str | None
    completed_component_ids: list[str]
    input_reliability: HybridInputReliability
    decision: HybridPedagogyDecision
    ordered_canvas_memory: list[OrderedCanvasMemoryItem]
    authored_support_content: list[HybridAuthoredSupportContent]
    active_action_ids: list[str]


class HybridSemanticEvaluation(GuidedLearningModel):
    pedagogical_state: HybridPedagogicalStateName
    completed_components: list[str]
    current_answer_step_index: int | None = Field(ge=0)
    current_answer_step_id: str | None


class HybridTutorWordingRequest(GuidedLearningModel):
    question: str = Field(min_length=1)
    resolved_student_meaning: str | None
    semantic_evaluation: HybridSemanticEvaluation
    decision: HybridPedagogyDecision
    canvas_actions: list[CanvasPedagogyAction]
    current_answer_step_id: str | None
    current_answer_step_text: str | None


class HybridTutorWording(GuidedLearningModel):
    tutor_voice_text: str = Field(min_length=1)


class CanvasPedagogyAction(GuidedLearningModel):
    action_id: str = Field(min_length=1)
    type: CanvasActionType
    layer: CanvasActionLayer
    target_object_id: str = Field(min_length=1)
    semantic_tag: CanvasSemanticTag
    text: str | None
    source_id: str | None
    answer_reveal_allowed: Literal[False]


class HybridTutorRequest(GuidedLearningModel):
    schema_version: Literal["1.0"]
    question_id: str = Field(min_length=1)
    question_type: QuestionType
    question: str = Field(min_length=1)
    answer_spec: AnswerSpec
    support_state: HybridSupportState
    session_history: list[ConversationMessage]
    ordered_canvas_memory: list[OrderedCanvasMemoryItem]
    student_evidence: HybridStudentEvidence
    pedagogical_state: HybridPedagogicalState

    @model_validator(mode="after")
    def validate_authored_answer_progression(self) -> HybridTutorRequest:
        authored_steps = authored_hybrid_answer_steps(self.answer_spec)
        _validate_hybrid_progression_state(
            authored_steps,
            self.pedagogical_state.completed_component_ids,
            self.pedagogical_state.current_answer_step_index,
            current_hybrid_answer_step_id(
                authored_steps,
                self.pedagogical_state.current_answer_step_index,
            ),
        )
        return self


class HybridTutorResponse(GuidedLearningModel):
    schema_version: Literal["1.0"]
    pedagogical_state: HybridPedagogicalStateName
    resolved_student_meaning: str | None
    input_reliability: HybridInputReliability
    tutor_voice_text: str = Field(min_length=1)
    canvas_actions: list[CanvasPedagogyAction]
    support_action: SupportUsed
    next_expected_input: HybridExpectedInput
    completed_components: list[str]
    current_answer_step_index: int | None = Field(ge=0)
    current_answer_step_id: str | None


def authored_hybrid_answer_steps(
    answer_spec: AnswerSpec,
) -> list[AuthoredAnswerStep]:
    """Derive stable ordered step and component IDs from authored step positions."""

    if not answer_spec.answer_steps:
        raise ValueError("Hybrid questions require at least one authored answer step.")
    authored_steps: list[AuthoredAnswerStep] = []
    for index, step_text in enumerate(answer_spec.answer_steps):
        if not step_text.strip():
            raise ValueError("Hybrid answer_steps cannot contain blank text.")
        authored_steps.append(
            AuthoredAnswerStep(
                step_id=f"{answer_spec.answer_spec_id}:STEP:{index + 1}",
                order_index=index,
                text=step_text,
                component_id=f"{answer_spec.answer_spec_id}:COMPONENT:{index + 1}",
            )
        )
    return authored_steps


def current_hybrid_answer_step_id(
    authored_steps: list[AuthoredAnswerStep],
    current_answer_step_index: int | None,
) -> str | None:
    if current_answer_step_index is None:
        return None
    if current_answer_step_index >= len(authored_steps):
        raise ValueError("current_answer_step_index is outside the authored answer steps.")
    return authored_steps[current_answer_step_index].step_id


def _validate_hybrid_progression_state(
    authored_steps: list[AuthoredAnswerStep],
    completed_component_ids: list[str],
    current_answer_step_index: int | None,
    current_answer_step_id: str | None,
) -> None:
    expected_completed_ids = [
        step.component_id for step in authored_steps[: len(completed_component_ids)]
    ]
    if completed_component_ids != expected_completed_ids:
        raise ValueError(
            "completed component IDs must be the ordered prefix of authored components."
        )
    expected_step_index = (
        None
        if len(completed_component_ids) == len(authored_steps)
        else len(completed_component_ids)
    )
    if current_answer_step_index != expected_step_index:
        raise ValueError(
            "current_answer_step_index must name the earliest unresolved authored step."
        )
    expected_step_id = current_hybrid_answer_step_id(
        authored_steps,
        current_answer_step_index,
    )
    if current_answer_step_id != expected_step_id:
        raise ValueError(
            "current_answer_step_id must match the earliest unresolved authored step."
        )


def validate_hybrid_tutor_progression(
    request: HybridTutorRequest,
    response: HybridTutorResponse,
) -> HybridTutorResponse:
    """Reject a Hybrid tutor result that skips, reorders, or forgets components."""

    authored_steps = authored_hybrid_answer_steps(request.answer_spec)
    _validate_hybrid_progression_state(
        authored_steps,
        response.completed_components,
        response.current_answer_step_index,
        response.current_answer_step_id,
    )
    previous_completed = request.pedagogical_state.completed_component_ids
    response_completed = response.completed_components
    if response_completed[: len(previous_completed)] != previous_completed:
        raise ValueError("Hybrid tutor response cannot remove confirmed components.")
    return response


class GeneratedConcept(GuidedLearningModel):
    concept_id: str
    description: str
    required: StrictBool


class GeneratedQuestionRubric(GuidedLearningModel):
    question_id: str
    required_concepts: list[GeneratedConcept]
    completion_rule: Literal["ALL_REQUIRED_CONCEPTS"]
    cache_key: str
    prompt_version: str


class ActiveTeachingObjective(GuidedLearningModel):
    objective_type: str
    target_concept_ids: list[str]
    confirmed_concept_ids: list[str]
    missing_concept_ids: list[str]


class GuidedEvaluation(GuidedLearningModel):
    student_state: GuidedStudentState
    newly_confirmed_concept_ids: list[str]
    preserved_concept_ids: list[str]
    contradicted_concept_ids: list[str]
    missing_concept_ids: list[str]
    selected_error_code: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    next_objective: ActiveTeachingObjective | None
    tutor_message: str = Field(min_length=1)
    tutor_message_voice: str = Field(min_length=1)


class ScaffoldEvaluationContext(GuidedLearningModel):
    scaffold_id: str
    step_id: str
    original_question: str
    canonical_answer: str
    accepted_answers: list[str]
    verification_method: str | None
    step_prompt: str
    expected_response_criterion: str
    completed_step_ids: list[str]


class ScaffoldStepEvaluation(GuidedLearningModel):
    step_satisfied: StrictBool
    original_answer_correct: StrictBool
    demonstrated_fact: str | None
    confidence: float = Field(ge=0.0, le=1.0)
