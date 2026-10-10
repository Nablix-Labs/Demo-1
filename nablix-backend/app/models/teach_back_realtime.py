from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.models.interaction import InteractionRequest
from app.models.teach_back import TeachBackReply


class TeachBackRealtimeStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    student_id: str


class TeachBackRealtimeReply(TeachBackReply):
    student_evidence: str | None = Field(description="Choose this FIRST. Copy a complete claim from the latest transcript that directly expresses or contradicts current_target.expected_concept, without adding quotation marks. Null for questions, unclear speech, or a correct statement about ONLY an already-completed concept. Never quote earlier turns or teaching context. Only a non-null relevant claim can have a graded verdict.")


class TeachBackRealtimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction: InteractionRequest
    teach_back_id: str
    micro_skill_id: str
    reply: TeachBackRealtimeReply


class TeachBackRealtimeContext(BaseModel):
    instructions: str
    teach_back_id: str
    micro_skill_id: str
    tool_name: str
    tool_description: str
    tool_parameters: dict[str, JsonValue]


class TeachBackRealtimeSession(BaseModel):
    client_secret: str
    calls_url: str
    response_timeout_seconds: int
    request_retry_count: int
    context: TeachBackRealtimeContext
