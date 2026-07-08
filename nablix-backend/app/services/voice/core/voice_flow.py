import time
import logging
import uuid

from adapter import STTAdapter, TTSAdapter, get_stt_adapter, get_tts_adapter
from contracts import (
    VoiceTranscriptRequest,
    VoiceTranscriptResponse,
    VoiceState,
    VoiceInteraction,
    VoiceStatus,
    FallbackMode,
    FallbackReason,
)
from errors import (
    VoiceError,
    EmptyTranscriptError,
    LowConfidenceError,
    STTProviderError,
    validate_voice_request,
)
import config

import mock_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("voice_flow")

MOCK_TUTOR_RESPONSES = {
    "x equals five": {
        "tutor_text": "Correct! x = 5 is right. Well done!",
        "tutor_voice": "Correct! x equals five is right. Well done!",
    },
    "x equals six": {
        "tutor_text": "Not quite. Check: 12 - 5 = ?. Try the subtraction again.",
        "tutor_voice": "Not quite. Check, twelve minus five equals what? Try the subtraction again.",
    },
    "can I get a hint": {
        "tutor_text": "Hint: To solve x + 5 = 12, subtract 5 from both sides.",
        "tutor_voice": "Here's a hint. To solve x plus five equals twelve, subtract five from both sides.",
    },
    "I don't understand": {
        "tutor_text": "That's okay! Let's break it down. We have x + 5 = 12. What operation undoes adding 5?",
        "tutor_voice": "That's okay! Let's break it down. We have x plus five equals twelve. What operation undoes adding five?",
    },
    "five over six": {
        "tutor_text": "5/6 — good. Now, what is 5/6 + 1/3?",
        "tutor_voice": "Five-sixths, good. Now, what is five-sixths plus one-third?",
    },
    "x times five plus y": {
        "tutor_text": "Do you mean x(5+y) or x·5 + y? Can you clarify?",
        "tutor_voice": "Do you mean x times the quantity five plus y, or x times five, plus y? Can you clarify?",
    },
}

DEFAULT_TUTOR_RESPONSE = {
    "tutor_text": "I heard you. Let me think about that...",
    "tutor_voice": "I heard you. Let me think about that.",
}

async def mock_tutor_evaluate(transcript: str) -> dict:
    return MOCK_TUTOR_RESPONSES.get(transcript, DEFAULT_TUTOR_RESPONSE)

async def mock_math_normalize(transcript: str, problem_context: str | None) -> str | None:
    normalizations = {
        "five over six": "5/6",
        "x equals five": "x = 5",
        "x equals six": "x = 6",
        "x times five plus y": "x*(5+y) or x*5+y",
        "x squared plus three": "x^2 + 3",
        "two thirds plus one fourth": "2/3 + 1/4",
    }
    return normalizations.get(transcript)

_sessions: dict[str, dict] = {}

def get_or_create_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "voice_state": VoiceState(),
            "interactions": [],
            "stt_provider": config.DEFAULT_STT_PROVIDER,
            "tts_provider": config.DEFAULT_TTS_PROVIDER,
        }
    return _sessions[session_id]

async def process_voice_input(request: VoiceTranscriptRequest) -> VoiceTranscriptResponse:
    total_start = time.time()
    session = get_or_create_session(request.session_id)

    try:
        validate_voice_request(
            request.session_id,
            request.audio_data,
            request.audio_format,
        )
        logger.info(f"[{request.session_id}] Voice input received")

        stt_adapter = get_stt_adapter(session["stt_provider"])
        logger.info(f"[{request.session_id}] STT provider: {stt_adapter.get_provider_name()}")

        try:
            stt_result = await stt_adapter.transcribe_audio(
                audio_data=request.audio_data,
                language=request.language,
                audio_format=request.audio_format,
                sample_rate=request.sample_rate,
            )
        except Exception as e:
            raise STTProviderError(stt_adapter.get_provider_name(), str(e))

        logger.info(
            f"[{request.session_id}] STT result: "
            f"transcript='{stt_result.transcript}', "
            f"confidence={stt_result.confidence:.2f}, "
            f"latency={stt_result.latency_ms}ms"
        )

        if not stt_result.transcript.strip():
            raise EmptyTranscriptError()

        if stt_result.confidence < config.CONFIDENCE_THRESHOLD:
            raise LowConfidenceError(stt_result.confidence, config.CONFIDENCE_THRESHOLD)

        normalized = await mock_math_normalize(
            stt_result.transcript,
            request.current_problem_context,
        )
        if normalized:
            logger.info(f"[{request.session_id}] Math normalized: '{stt_result.transcript}' → '{normalized}'")

        tutor_result = await mock_tutor_evaluate(stt_result.transcript)
        logger.info(f"[{request.session_id}] Tutor response: {tutor_result['tutor_text'][:60]}...")

        tts_adapter = get_tts_adapter(session["tts_provider"])
        logger.info(f"[{request.session_id}] TTS provider: {tts_adapter.get_provider_name()}")

        audio_url = None
        tts_latency = None
        try:
            tts_result = await tts_adapter.generate_speech(
                text=tutor_result["tutor_voice"],
                voice=config.TTS_VOICE,
                audio_format=config.TTS_AUDIO_FORMAT,
            )
            audio_url = str(tts_result.audio_data)
            tts_latency = tts_result.latency_ms
            logger.info(
                f"[{request.session_id}] TTS generated: "
                f"duration={tts_result.duration_seconds}s, "
                f"latency={tts_result.latency_ms}ms"
            )
        except Exception as e:
            logger.warning(f"[{request.session_id}] TTS failed: {e}. Falling back to text.")

        total_ms = int((time.time() - total_start) * 1000)

        response = VoiceTranscriptResponse(
            session_id=request.session_id,
            raw_transcript=stt_result.transcript,
            transcript_confidence=stt_result.confidence,
            normalized_expression=normalized,
            tutor_response_text=tutor_result["tutor_text"],
            tutor_response_voice=tutor_result["tutor_voice"],
            audio_response_url=audio_url,
            voice_status=VoiceStatus.ACTIVE,
            needs_clarification=False,
            fallback_mode=FallbackMode.NONE,
            stt_latency_ms=stt_result.latency_ms,
            tts_latency_ms=tts_latency,
            total_latency_ms=total_ms,
        )

        session["voice_state"].status = VoiceStatus.ACTIVE
        session["voice_state"].last_transcript = stt_result.transcript
        session["voice_state"].last_normalized_expression = normalized
        session["voice_state"].transcript_confidence = stt_result.confidence
        session["voice_state"].last_audio_response_url = audio_url
        session["voice_state"].interaction_count += 1

        interaction = VoiceInteraction(
            interaction_id=str(uuid.uuid4())[:8],
            session_id=request.session_id,
            raw_transcript=stt_result.transcript,
            transcript_confidence=stt_result.confidence,
            normalized_expression=normalized,
            tutor_response_text=tutor_result["tutor_text"],
            tutor_response_voice=tutor_result["tutor_voice"],
            audio_response_url=audio_url,
            stt_latency_ms=stt_result.latency_ms,
            tts_latency_ms=tts_latency,
            total_latency_ms=total_ms,
        )
        session["interactions"].append(interaction)

        logger.info(f"[{request.session_id}] Voice flow complete. Total: {total_ms}ms")
        return response

    except VoiceError as e:
        total_ms = int((time.time() - total_start) * 1000)
        logger.warning(f"[{request.session_id}] Voice error: {e.message}")

        fallback_mode = FallbackMode(e.fallback_mode) if e.fallback_mode != "NONE" else FallbackMode.NONE

        if isinstance(e, EmptyTranscriptError):
            reason = FallbackReason.EMPTY_TRANSCRIPT
        elif isinstance(e, LowConfidenceError):
            reason = FallbackReason.LOW_CONFIDENCE
        else:
            reason = FallbackReason.PROVIDER_ERROR

        return VoiceTranscriptResponse(
            session_id=request.session_id,
            raw_transcript="",
            transcript_confidence=0.0,
            tutor_response_text=e.message,
            tutor_response_voice=e.message,
            voice_status=VoiceStatus.ACTIVE,
            needs_clarification=True,
            fallback_mode=fallback_mode,
            fallback_reason=reason,
            total_latency_ms=total_ms,
        )

    except Exception as e:
        total_ms = int((time.time() - total_start) * 1000)
        logger.error(f"[{request.session_id}] Unexpected error: {e}")

        return VoiceTranscriptResponse(
            session_id=request.session_id,
            raw_transcript="",
            transcript_confidence=0.0,
            tutor_response_text="Something went wrong with voice. Please type your answer instead.",
            tutor_response_voice="Something went wrong with voice. Please type your answer instead.",
            voice_status=VoiceStatus.FAILED,
            needs_clarification=False,
            fallback_mode=FallbackMode.TEXT,
            fallback_reason=FallbackReason.PROVIDER_ERROR,
            total_latency_ms=total_ms,
        )
