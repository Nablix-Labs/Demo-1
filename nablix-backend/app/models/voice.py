from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.models.fields import BoundedText, NonEmptyText, SessionId, StudentId


class VoiceRequest(BaseModel):
    """Validated request to transcribe a spoken student answer."""

    session_id: SessionId
    student_id: StudentId
    audio_reference: NonEmptyText


class VoiceTTSRequest(BaseModel):
    """Text to synthesize into tutor speech (e.g. for the Canvas Check button)."""

    text: NonEmptyText


class VoiceResponse(BaseModel):
    """Transcription result returned to the caller."""

    session_id: str
    student_id: str
    transcript: str
    confidence: float
    language: str


class VoiceSessionStartRequest(BaseModel):
    """Request to open a voice stream for an existing tutoring session."""

    session_id: SessionId
    student_id: StudentId


class VoiceSessionStartResponse(BaseModel):
    """Mock voice stream metadata returned to the frontend."""

    session_id: str
    student_id: str
    stream_active: bool
    current_turn: Literal["STUDENT", "TUTOR"]
    voice_session_token: str
    fallback_active: bool


class VoiceTranscriptRequest(BaseModel):
    """Internal transcript payload emitted after one student voice turn."""

    session_id: SessionId
    student_id: StudentId
    transcript: BoundedText
    confidence: float
    audio_duration_seconds: float
    turn: Literal["STUDENT"]
    timestamp: datetime

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0.")
        return value

    @field_validator("audio_duration_seconds")
    @classmethod
    def validate_audio_duration_seconds(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("audio_duration_seconds must be greater than 0.")
        return value
