from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool

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
    raw_ocr_text: str | None
    processed_math_text: str | None
    ocr_confidence: float | None = Field(ge=0.0, le=1.0)
    canvas_object_ids: list[str]


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
    component_ids: list[str]
    current_answer_step_index: int | None = Field(ge=0)
    completed_component_ids: list[str]
    support_state: HybridSupportState
    session_history: list[ConversationMessage]
    ordered_canvas_memory: list[OrderedCanvasMemoryItem]
    student_evidence: HybridStudentEvidence
    pedagogical_state: HybridPedagogicalState


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
