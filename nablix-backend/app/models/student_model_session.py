from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


StudentModelPhase = Literal[
    "PHASE_0_DIAGNOSTIC",
    "PHASE_1_ORIENTATION",
    "PHASE_2_GUIDED_LEARNING",
    "PHASE_3_INDEPENDENT_PRACTICE",
    "REVIEW",
]
DiagnosticResult = Literal["CORRECT", "INCORRECT"]
SupportUsed = Literal[
    "NONE",
    "HINT",
    "VISUAL_CUE",
    "SCAFFOLD",
    "PARALLEL_EXAMPLE",
    "TUTOR_SOLVED",
]


class MicroSkillMapping(BaseModel):
    micro_skill_id: str
    is_primary: bool
    weight: float


class QuestionOption(BaseModel):
    option_id: str
    text: str


class StudentQuestionView(BaseModel):
    question_text: str
    question_type: str
    options: list[QuestionOption]
    requires_student_response: bool


class AnswerSpec(BaseModel):
    answer_spec_id: str
    canonical_answer: str
    accepted_answers: list[str]
    verification_method: str


class TutorQuestionView(BaseModel):
    model_config = ConfigDict(extra="allow")

    answer_spec: AnswerSpec
    potential_errors: list[dict[str, object]] = Field(default_factory=list)


class StudentModelQuestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    question_id: str
    question_usage_id: str
    difficulty: int
    item_family_id: str
    question_role: str
    support_policy: str
    diagnosis_policy: str
    max_attempts: int
    micro_skill_mappings: list[MicroSkillMapping]
    student_view: StudentQuestionView
    tutor_view: TutorQuestionView


class QuestionSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    difficulty_policy: str | None = None
    questions: list[StudentModelQuestion]


class OrientationVideo(BaseModel):
    video_id: str
    title: str
    asset_url: str | None
    duration_seconds: int | None


class WorkedExampleStep(BaseModel):
    step_id: str
    sequence_no: int
    screen_content: str | None
    narration_text: str | None
    must_show: str | None
    must_not_show: str | None


class WorkedExample(BaseModel):
    worked_example_id: str
    title: str
    covered_micro_skill_ids: list[str]
    final_answer: str | None
    student_answer_required: bool
    steps: list[WorkedExampleStep]


class OrientationDeliveryItem(BaseModel):
    sequence_no: int
    content_type: Literal["ORIENTATION_VIDEO", "WORKED_EXAMPLE"]
    video: OrientationVideo | None = None
    worked_example: WorkedExample | None = None


class OrientationBundle(BaseModel):
    target_micro_skill_ids: list[str]
    delivery_sequence: list[OrientationDeliveryItem]


class StudentModelPhasePayload(BaseModel):
    phase: StudentModelPhase
    payload_type: str
    question_set: QuestionSet | None = None
    orientation_bundle: OrientationBundle | None = None
    support_to_serve: dict[str, object] | None = None
    rescue_to_serve: dict[str, object] | None = None
    review_summary: dict[str, object] | None = None


class StudentModelRouting(BaseModel):
    reason_code: str
    reason: str
    next_action: str
    next_topic_id: str | None = None
    next_topic_entry_phase: StudentModelPhase | None = None
    prerequisite_check_required: bool
    prerequisite_micro_skill_ids: list[str]
    content_gap_detected: bool
    missing_micro_skill_ids: list[str]


class StudentModelStatus(BaseModel):
    success: bool
    status_code: str
    intervention_required: bool
    intervention_reason: str | None
    warnings: list[object]
    operational_errors: list[object]


class JourneyPhaseState(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    phase_visit_no: int | None
    target_micro_skill_ids: list[str] = Field(default_factory=list)
    completed_micro_skill_ids: list[str] = Field(default_factory=list)
    remaining_micro_skill_ids: list[str] = Field(default_factory=list)
    verified_micro_skill_ids: list[str] = Field(default_factory=list)
    unresolved_micro_skill_ids: list[str] = Field(default_factory=list)
    retry_required_micro_skill_ids: list[str] = Field(default_factory=list)
    highest_support_used_by_skill: dict[str, SupportUsed] = Field(default_factory=dict)
    current_question_id: str | None = None
    used_question_ids: list[str] = Field(default_factory=list)


class StudentModelJourneyState(BaseModel):
    model_config = ConfigDict(extra="allow")

    student_id: str
    active_session_id: str
    topic_id: str
    topic_status: str
    mastery_status: str
    continuity_status: str
    current_phase: StudentModelPhase
    recommended_entry_phase: StudentModelPhase | None
    session_count: int
    started_at: str
    last_activity_at: str
    phase_0_diagnostic: JourneyPhaseState
    phase_1_orientation: JourneyPhaseState
    phase_2_guided_learning: JourneyPhaseState
    phase_3_independent_practice: JourneyPhaseState
    review: JourneyPhaseState
    version: int
    updated_at: str


class StudentModelSessionEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["3.0"]
    request_id: str
    processed_at: str
    journey_state: StudentModelJourneyState
    phase_payload: StudentModelPhasePayload | None
    event_result: dict[str, object] | None
    routing: StudentModelRouting
    status: StudentModelStatus


class PublicStudentModelQuestion(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    question_id: str
    student_view: StudentQuestionView


class PublicQuestionSet(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    questions: list[PublicStudentModelQuestion]


class PublicStudentModelPhasePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    phase: StudentModelPhase
    payload_type: str
    question_set: PublicQuestionSet | None = None
    orientation_bundle: OrientationBundle | None = None


class PublicStudentModelJourney(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    topic_id: str


class PublicStudentModelEvent(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    schema_version: Literal["3.0"]
    request_id: str
    processed_at: str
    journey_state: PublicStudentModelJourney
    phase_payload: PublicStudentModelPhasePayload | None


class SessionEventBase(BaseModel):
    request_id: str
    event_type: str
    topic_id: str
    student_id: str
    timestamp: str


class DiagnosticQuestionSetRequestedEvent(SessionEventBase):
    event_type: Literal["DIAGNOSTIC_QUESTION_SET_REQUESTED"]


class MicroSkillResult(BaseModel):
    micro_skill_id: str
    result: DiagnosticResult


class DiagnosticCompletedEvent(SessionEventBase):
    event_type: Literal["DIAGNOSTIC_COMPLETED"]
    micro_skill_results: list[MicroSkillResult]


class WorkedExampleRequestedEvent(SessionEventBase):
    event_type: Literal["WORKED_EXAMPLE_REQUESTED"]
    target_micro_skill_ids: list[str]


class OrientationCompletedEvent(SessionEventBase):
    event_type: Literal["ORIENTATION_COMPLETED"]
    target_micro_skill_ids: list[str]


class GuidedAttemptEvent(SessionEventBase):
    event_type: Literal["CORRECT_ATTEMPT", "INCORRECT_ATTEMPT"]
    question_id: str
    micro_skill_ids: list[str]
    student_response: str
    support_used: SupportUsed | None = None
    error_code: str | None = None


class GuidedSupportEvent(SessionEventBase):
    event_type: Literal[
        "GUIDED_SUPPORT_ESCALATION_REQUIRED",
        "MAXIMUM_GUIDED_SUPPORT_REQUIRED",
    ]
    question_id: str
    micro_skill_id: str


class GuidedPhaseCompletedEvent(SessionEventBase):
    event_type: Literal["GUIDED_PHASE_COMPLETED"]
    completed_micro_skill_ids: list[str]


class IndependentRetryCompletedEvent(SessionEventBase):
    event_type: Literal["INDEPENDENT_RETRY_COMPLETED"]
    question_id: str
    micro_skill_ids: list[str]
    student_response: str
    independent_success: bool
    error_code: str | None = None


class GuidedQuestionSetRequestedEvent(SessionEventBase):
    event_type: Literal["GUIDED_QUESTION_SET_REQUESTED"]
    target_micro_skill_ids: list[str]


StudentModelSessionEvent: TypeAlias = (
    DiagnosticQuestionSetRequestedEvent
    | DiagnosticCompletedEvent
    | WorkedExampleRequestedEvent
    | OrientationCompletedEvent
    | GuidedAttemptEvent
    | GuidedSupportEvent
    | GuidedPhaseCompletedEvent
    | IndependentRetryCompletedEvent
    | GuidedQuestionSetRequestedEvent
)


class StudentModelCoreState(BaseModel):
    student_id: str
    topic_id: str
    current_phase: StudentModelPhase
    mastery_status: str
    continuity_status: str
    recommended_entry_phase: StudentModelPhase | None
    target_micro_skill_ids: list[str]
    completed_micro_skill_ids: list[str]
    independently_verified_micro_skill_ids: list[str]
    unresolved_micro_skill_ids: list[str]
    highest_support_used_by_skill: dict[str, SupportUsed]
    used_question_ids: list[str]
    current_question_id: str | None
    transition_reason: str
    next_topic_recommendation: str | None
