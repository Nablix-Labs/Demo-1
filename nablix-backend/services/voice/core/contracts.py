from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class InputSource(str, Enum):
    VOICE = "VOICE"
    TEXT = "TEXT"

class VoiceStatus(str, Enum):
    INACTIVE = "INACTIVE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    PROCESSING = "PROCESSING"
    RESPONDING = "RESPONDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"

class FallbackMode(str, Enum):
    NONE = "NONE"
    TEXT = "TEXT"
    REPEAT = "REPEAT"

class FallbackReason(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    EMPTY_TRANSCRIPT = "EMPTY_TRANSCRIPT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_AUDIO = "INVALID_AUDIO"
    SILENCE_DETECTED = "SILENCE_DETECTED"
    AMBIGUOUS_MATH = "AMBIGUOUS_MATH"

class VoiceTranscriptRequest(BaseModel):
    session_id: str = Field(
        description="Active tutoring session ID"
    )
    audio_data: str | bytes = Field(
        description="Audio content — mock string for Day 1, real bytes later"
    )
    input_source: InputSource = Field(
        default=InputSource.VOICE,
        description="How the input arrived (VOICE or TEXT)"
    )
    language: str = Field(
        default="en",
        description="Language code — English only for MVP"
    )
    audio_format: str = Field(
        default="wav",
        description="Audio format — wav, mp3, webm, etc."
    )
    sample_rate: int = Field(
        default=16000,
        description="Audio sample rate in Hz — 16kHz is standard for speech"
    )
    current_problem_context: str | None = Field(
        default=None,
        description="The math problem the student is currently working on. "
                    "Used by the math normalizer to disambiguate spoken math. "
                    "e.g., 'Solve: x + 5 = 12'"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="When the audio was captured"
    )

class VoiceTranscriptResponse(BaseModel):
    session_id: str
    raw_transcript: str = Field(
        description="Exact text from STT — e.g., 'five over six'"
    )
    transcript_confidence: float = Field(
        description="STT confidence score, 0.0 to 1.0"
    )
    normalized_expression: str | None = Field(
        default=None,
        description="Symbolic math form — e.g., '5/6'. "
                    "None if no math was detected in the transcript."
    )
    tutor_response_text: str = Field(
        description="Tutor's response for screen display — may contain symbols"
    )
    tutor_response_voice: str = Field(
        description="Tutor's response for speaking — math pronounced naturally"
    )
    audio_response_url: str | None = Field(
        default=None,
        description="URL or path to the generated audio file. "
                    "None if TTS failed and we fell back to text."
    )
    voice_status: VoiceStatus = Field(
        default=VoiceStatus.ACTIVE,
        description="Current voice session state"
    )
    needs_clarification: bool = Field(
        default=False,
        description="True if transcript was ambiguous and we need the student "
                    "to clarify (either low confidence audio or ambiguous math)"
    )
    fallback_mode: FallbackMode = Field(
        default=FallbackMode.NONE,
        description="Whether to fall back to text or ask to repeat"
    )
    fallback_reason: FallbackReason | None = Field(
        default=None,
        description="Why fallback was triggered, if applicable"
    )
    stt_latency_ms: int | None = Field(
        default=None,
        description="How long STT took in milliseconds"
    )
    tts_latency_ms: int | None = Field(
        default=None,
        description="How long TTS took in milliseconds"
    )
    total_latency_ms: int | None = Field(
        default=None,
        description="Total voice round-trip time in milliseconds"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

class VoiceState(BaseModel):
    status: VoiceStatus = Field(
        default=VoiceStatus.INACTIVE,
        description="Current voice state"
    )
    last_transcript: str | None = Field(
        default=None,
        description="Most recent transcript from the student"
    )
    last_normalized_expression: str | None = Field(
        default=None,
        description="Most recent normalized math expression"
    )
    transcript_confidence: float | None = Field(
        default=None,
        description="Confidence of the most recent transcript"
    )
    fallback_mode: FallbackMode = Field(
        default=FallbackMode.NONE
    )
    last_audio_response_url: str | None = Field(
        default=None,
        description="URL of the most recent audio response"
    )
    interaction_count: int = Field(
        default=0,
        description="Number of voice interactions in this session"
    )

class VoiceInteraction(BaseModel):
    interaction_id: str
    session_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input_source: InputSource = Field(default=InputSource.VOICE)
    raw_transcript: str
    transcript_confidence: float
    normalized_expression: str | None = None
    tutor_response_text: str
    tutor_response_voice: str
    audio_response_url: str | None = None
    fallback_used: bool = False
    fallback_reason: FallbackReason | None = None
    stt_latency_ms: int | None = None
    tts_latency_ms: int | None = None
    total_latency_ms: int | None = None

class VoiceSessionStartRequest(BaseModel):
    session_id: str
    language: str = "en"
    preferred_stt_provider: str | None = Field(
        default=None,
        description="Which STT to use — 'deepgram', 'faster_whisper', or None for default"
    )
    preferred_tts_provider: str | None = Field(
        default=None,
        description="Which TTS to use — 'deepgram', 'openai', or None for default"
    )

class VoiceSessionStartResponse(BaseModel):
    session_id: str
    voice_status: VoiceStatus = VoiceStatus.ACTIVE
    stt_provider: str = Field(description="Which STT provider is active")
    tts_provider: str = Field(description="Which TTS provider is active")
    message: str = "Voice session started"

class VoiceSessionEndRequest(BaseModel):
    session_id: str

class VoiceSessionEndResponse(BaseModel):
    session_id: str
    voice_status: VoiceStatus = VoiceStatus.INACTIVE
    total_interactions: int
    message: str = "Voice session ended"
