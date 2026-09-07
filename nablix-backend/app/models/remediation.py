"""Phase 3 repeated-failure remediation, in the shape the frontend reads.

Names and codes here are the spec's (§11) and the ones `Numera-ui`'s
`lib/phase3Routing.ts` already ships against. The backend does not invent a
second vocabulary: `selection_options[].code`/`label`, not `reason_options`/
`text`, because a parallel naming is what strands the popup.

Routing itself remains Student Model-owned; this module only types it.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.fields import NonEmptyText


InterventionReason = Literal[
    "DONT_UNDERSTAND_QUESTION",
    "DONT_KNOW_HOW_TO_START",
    "CANNOT_APPLY_IDEA",
    "WORDS_SYMBOLS_CONFUSING",
    "WORKING_MISTAKES",
    "OTHER",
]

INTERVENTION_PROMPT = "What are you finding difficult?"

# Mirrors DEFAULT_INTERVENTION_OPTIONS in Numera-ui/lib/phase3Routing.ts. The
# frontend keeps its own copy as a never-empty fallback; these are the ones a
# submission is actually validated against.
INTERVENTION_OPTIONS: list[tuple[InterventionReason, str]] = [
    ("DONT_UNDERSTAND_QUESTION", "I do not understand what the question is asking."),
    ("DONT_KNOW_HOW_TO_START", "I do not know how to start."),
    ("CANNOT_APPLY_IDEA", "I understand the idea, but I cannot use it in this question."),
    ("WORDS_SYMBOLS_CONFUSING", "The maths words or symbols are confusing."),
    ("WORKING_MISTAKES", "I keep making calculation or working mistakes."),
    ("OTHER", "Something else."),
]


class Phase3Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: NonEmptyText
    micro_skill_id: NonEmptyText
    phase_visit_no: int = Field(ge=1)
    question_position_no: int = Field(ge=1)
    checkpoint_question_id: NonEmptyText
    question_usage_id: NonEmptyText


class InterventionVoiceInput(BaseModel):
    """The optional spoken half of the student's answer.

    `audio_ref` is always null from the browser -- there is no audio upload
    anywhere in the frontend, so the transcript is the evidence. Accepting the
    null rather than demanding a reference is the whole of ask 6.
    """

    model_config = ConfigDict(extra="forbid")

    provided: bool = False
    audio_ref: NonEmptyText | None = None
    transcript: NonEmptyText | None = None


class InterventionFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_reason_codes: list[InterventionReason] = Field(min_length=1)
    voice_input: InterventionVoiceInput | None = None

    @field_validator("selected_reason_codes")
    @classmethod
    def normalize_reasons(cls, values: list[InterventionReason]) -> list[InterventionReason]:
        return sorted(set(values))


class StudentModelIntervention(BaseModel):
    """The authoritative case, as Student Model reports it. Never public."""

    model_config = ConfigDict(extra="forbid")

    intervention_id: NonEmptyText
    topic_id: NonEmptyText
    micro_skill_id: NonEmptyText
    reason_code: Literal["AUTOMATED_REMEDIATION_EXHAUSTED"]
    state: Literal["ACTIVE", "RESOLVED"]
    feedback: InterventionFeedback | None = None


class InterventionSelectionOption(BaseModel):
    code: InterventionReason
    label: str


class InterventionInputRequest(BaseModel):
    """Spec §11 popup, carried on the public phase payload (TC-33)."""

    intervention_id: NonEmptyText
    prompt: str = INTERVENTION_PROMPT
    selection_required: bool = True
    voice_input_enabled: bool = True
    voice_input_required: bool = False
    selection_options: list[InterventionSelectionOption]


def intervention_input_request(state: StudentModelIntervention) -> InterventionInputRequest:
    """The popup for an active case, with the student's own evidence withheld."""

    return InterventionInputRequest(
        intervention_id=state.intervention_id,
        selection_options=[
            InterventionSelectionOption(code=code, label=label)
            for code, label in INTERVENTION_OPTIONS
        ],
    )
