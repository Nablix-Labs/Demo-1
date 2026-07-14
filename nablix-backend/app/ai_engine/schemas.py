from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


EvaluationCategory = Literal[
    "CORRECT",
    "PARTIALLY_CORRECT",
    "INCORRECT",
    "UNCLEAR",
    "NO_ATTEMPT",
    "IRRELEVANT",
]

ErrorType = Literal[
    "ARITHMETIC_ERROR",
    "SIGN_ERROR",
    "OPPOSITE_OPERATION_ERROR",
    "CONCEPTUAL_MISUNDERSTANDING",
    "PROCEDURAL_ERROR",
    "NOTATION_ISSUE",
    "INSUFFICIENT_INFORMATION",
    "UNKNOWN_ERROR",
]

IntentType = Literal[
    "SUBMITTING_ANSWER",
    "ASKING_QUESTION",
    "EXPRESSING_CONFUSION",
    "REQUESTING_HINT",
    "REQUESTING_ANSWER",
    "ATTEMPTING_OVERRIDE",
    "OFF_TOPIC",
]

ResponseStrategy = Literal[
    "GUIDED_HINT",
    "SCAFFOLD",
    "CLARIFY",
    "CONFIRM_CORRECT",
    "ENCOURAGE_RETRY",
    "PROVIDE_VISUAL_CUE",
    "PROVIDE_WORKED_EXAMPLE",
    "DIAGNOSTIC_PROMPT",
    "MASTERY_CONFIRM",
    "SAFETY_RESPONSE",
]

InputSource = Literal["TEXT", "VOICE", "CANVAS"]

LearningPhase = Literal[
    "DIAGNOSTIC",
    "CONCEPT_ORIENTATION",
    "GUIDED_PRACTICE",
    "INDEPENDENT_PRACTICE",
    "REVIEW",
]

LearningEventType = Literal[
    "CORRECT_ATTEMPT",
    "INCORRECT_ATTEMPT",
    "PARTIAL_ATTEMPT",
    "HINT_USED",
    "SCAFFOLD_STEP_DELIVERED",
    "VISUAL_CUE_SHOWN",
    "CANVAS_SUBMITTED",
    "SESSION_STARTED",
    "SESSION_ENDED",
    "PHASE_TRANSITION",
    "MASTERY_ACHIEVED",
    "SAFETY_FLAG",
    "VOICE_FALLBACK",
]

VisualCueType = Literal[
    "EQUATION_BLOCK",
    "NUMBER_LINE",
    "GRAPH",
    "TABLE",
    "HIGHLIGHTED_STEP",
    "CONCEPT_CARD",
]

CanvasStepEvaluation = Literal["CORRECT", "INCORRECT"]
HighlightType = Literal["ERROR"]
HighlightColour = Literal["RED"]
HintLevel = Literal[1, 2, 3]
MistakeStatus = Literal["mistake_found", "no_mistake", "uncertain"]
AnnotationIntentKind = Literal["circle_target", "write_correction", "draw_arrow"]
AnnotationPlacement = Literal["right", "below"]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VisualCue(StrictSchema):
    show: StrictBool
    cue_type: VisualCueType | None
    description: str | None


class HighlightInstruction(StrictSchema):
    step_number: int = Field(ge=1)
    highlight_type: HighlightType
    colour: HighlightColour


class CanvasStepFeedback(StrictSchema):
    step_number: int = Field(ge=1)
    evaluation: CanvasStepEvaluation
    error_type: ErrorType | None
    feedback: str | None


class CanvasFeedback(StrictSchema):
    has_feedback: StrictBool
    step_feedback: list[CanvasStepFeedback]
    highlight_instruction: HighlightInstruction | None


class CanvasTextRegion(StrictSchema):
    step_id: str | None
    text: str
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class CanvasMistakeClassification(StrictSchema):
    status: MistakeStatus
    mistake_step_id: str | None
    target_text: str | None
    target_span: list[int] | None
    replacement_text: str | None
    confidence: float = Field(ge=0.0, le=1.0)


class CanvasAnnotationIntent(StrictSchema):
    kind: AnnotationIntentKind
    target_step_id: str
    text: str | None
    placement: AnnotationPlacement | None


class CanvasMathReview(StrictSchema):
    error_type: ErrorType | None
    tutor_feedback: str | None
    canvas_feedback: CanvasFeedback
    mistake_classification: CanvasMistakeClassification
    annotation_intents: list[CanvasAnnotationIntent]


class SafetyCheck(StrictSchema):
    passed: StrictBool
    flag_type: str | None
    action_taken: str | None


class GuardrailCheck(StrictSchema):
    passed: StrictBool
    violation_type: str | None
    action_taken: str | None


class StudentModelEvent(StrictSchema):
    event_type: LearningEventType
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    hint_level_used: int = Field(ge=0, le=3)
    independent_success: StrictBool


class TutorResponse(StrictSchema):
    evaluation: EvaluationCategory | None
    error_type: ErrorType | None
    intent: IntentType
    response_strategy: ResponseStrategy
    tutor_message: str
    tutor_message_voice_optimised: str
    voice_optimised: StrictBool
    hint_level: HintLevel | None
    scaffold_steps_delivered: list[str]
    visual_cue: VisualCue
    canvas_feedback: CanvasFeedback
    mistake_classification: CanvasMistakeClassification | None
    annotation_intents: list[CanvasAnnotationIntent]
    next_phase_recommendation: LearningPhase
    answer_reveal_allowed: StrictBool
    confidence: float = Field(ge=0.0, le=1.0)
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    safety_check: SafetyCheck
    guardrail_check: GuardrailCheck
    student_model_events: list[StudentModelEvent]
