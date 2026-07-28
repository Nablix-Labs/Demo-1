from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StudentModelSessionEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    student_id: str = Field(min_length=1)
    timestamp: str | None = None


class StudentModelPhasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    phase: str
    payload_type: str
    question_set: dict[str, JsonValue] | None = None
    orientation_bundle: dict[str, JsonValue] | None = None
    support_to_serve: dict[str, JsonValue] | None = None
    rescue_to_serve: dict[str, JsonValue] | None = None
    review_summary: dict[str, JsonValue] | None = None


class StudentModelRouting(BaseModel):
    model_config = ConfigDict(extra="allow")

    reason_code: str
    reason: str
    next_action: str
    next_topic_id: str | None = None
    next_topic_entry_phase: str | None = None
    prerequisite_check_required: bool = False
    prerequisite_micro_skill_ids: list[str] = Field(default_factory=list)
    content_gap_detected: bool = False
    missing_micro_skill_ids: list[str] = Field(default_factory=list)


class StudentModelStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    status_code: str
    intervention_required: bool
    intervention_reason: str | None = None
    warnings: list[JsonValue] = Field(default_factory=list)
    operational_errors: list[JsonValue] = Field(default_factory=list)


class StudentModelSessionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    request_id: str
    processed_at: str
    journey_state: dict[str, JsonValue]
    phase_payload: StudentModelPhasePayload | None = None
    event_result: dict[str, JsonValue] | None = None
    routing: StudentModelRouting
    status: StudentModelStatus
