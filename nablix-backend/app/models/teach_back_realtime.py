from pydantic import BaseModel, ConfigDict

from app.models.interaction import InteractionRequest
from app.models.teach_back import TeachBackReply


class TeachBackRealtimeStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    student_id: str


class TeachBackRealtimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction: InteractionRequest
    teach_back_id: str
    micro_skill_id: str
    reply: TeachBackReply


class TeachBackRealtimeContext(BaseModel):
    instructions: str
    teach_back_id: str
    micro_skill_id: str
    tool_name: str


class TeachBackRealtimeSession(BaseModel):
    client_secret: str
    calls_url: str
    response_timeout_seconds: int
    request_retry_count: int
    context: TeachBackRealtimeContext
