from pydantic import BaseModel, ConfigDict


class TeachBackRealtimeStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    student_id: str


class TeachBackRealtimeSession(BaseModel):
    client_secret: str
    calls_url: str
    response_timeout_seconds: int
    request_retry_count: int
    speaker_instructions: str
