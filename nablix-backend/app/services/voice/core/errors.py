class VoiceError(Exception):

    def __init__(self, message: str, fallback_mode: str = "TEXT"):
        self.message = message
        self.fallback_mode = fallback_mode
        super().__init__(self.message)

class MissingSessionError(VoiceError):

    def __init__(self, session_id: str | None = None):
        msg = f"Missing or invalid session ID: {session_id}"
        super().__init__(msg, fallback_mode="TEXT")

class MissingAudioError(VoiceError):

    def __init__(self):
        super().__init__(
            "No audio data provided. Please speak or switch to text input.",
            fallback_mode="TEXT",
        )

class InvalidAudioFormatError(VoiceError):

    SUPPORTED_FORMATS = ["wav", "mp3", "webm", "ogg", "flac"]

    def __init__(self, format: str):
        super().__init__(
            f"Audio format '{format}' not supported. "
            f"Supported: {self.SUPPORTED_FORMATS}",
            fallback_mode="TEXT",
        )

class EmptyTranscriptError(VoiceError):

    def __init__(self):
        super().__init__(
            "I didn't hear anything. Could you try speaking again?",
            fallback_mode="REPEAT",
        )

class LowConfidenceError(VoiceError):

    def __init__(self, confidence: float, threshold: float):
        super().__init__(
            f"I'm not fully sure I heard that clearly (confidence: {confidence:.0%}). "
            f"Can you repeat it or type your answer?",
            fallback_mode="REPEAT",
        )
        self.confidence = confidence
        self.threshold = threshold

class STTProviderError(VoiceError):

    def __init__(self, provider: str, detail: str = ""):
        msg = f"Speech-to-text provider '{provider}' failed"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, fallback_mode="TEXT")
        self.provider = provider

class TTSProviderError(VoiceError):

    def __init__(self, provider: str, detail: str = ""):
        msg = f"Text-to-speech provider '{provider}' failed"
        if detail:
            msg += f": {detail}"
        super().__init__(msg, fallback_mode="NONE")
        self.provider = provider

class MathNormalizationError(VoiceError):

    def __init__(self, transcript: str):
        super().__init__(
            f"I wasn't sure how to interpret the math in '{transcript}'. "
            f"Could you say it differently or type it?",
            fallback_mode="REPEAT",
        )

def validate_voice_request(session_id: str | None, audio_data, audio_format: str):
    if not session_id or not session_id.strip():
        raise MissingSessionError(session_id)

    if audio_data is None or (isinstance(audio_data, str) and not audio_data.strip()):
        raise MissingAudioError()

    if isinstance(audio_data, bytes) and len(audio_data) == 0:
        raise MissingAudioError()

    if audio_format not in InvalidAudioFormatError.SUPPORTED_FORMATS:
        raise InvalidAudioFormatError(audio_format)
