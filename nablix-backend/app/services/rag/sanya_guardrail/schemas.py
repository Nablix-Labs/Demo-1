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
    next_phase_recommendation: LearningPhase
    answer_reveal_allowed: StrictBool
    confidence: float = Field(ge=0.0, le=1.0)
    input_source: InputSource
    transcript_confidence: float | None = Field(ge=0.0, le=1.0)
    safety_check: SafetyCheck
    guardrail_check: GuardrailCheck
    student_model_events: list[StudentModelEvent]
