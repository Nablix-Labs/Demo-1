import os
import sys
import json
import time
import asyncio
import ssl
import certifi
import logging
import base64
from enum import Enum
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

import websockets
# Explicit: the websockets package lazy-loads submodules, so
# `websockets.exceptions` only resolves after something has touched it.
# Both receiver loops catch ConnectionClosed, and an unresolved attribute
# inside an `except` clause would mask the real error. Importing it here
# makes that impossible.
import websockets.exceptions

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "adapters"))

import config as voice_config

from adapter import get_tts_adapter

import mock_adapter

if voice_config.OPENAI_API_KEY:
    import openai_tts_adapter

if voice_config.DEEPGRAM_API_KEY:
    import deepgram_tts_adapter

if voice_config.CARTESIA_API_KEY:
    import cartesia_tts_adapter

if voice_config.INWORLD_API_KEY:
    import inworld_tts_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _websocket_is_connected(ws: WebSocket) -> bool:
    """Return whether both sides of the ASGI WebSocket remain connected."""
    client_state = getattr(ws, "client_state", WebSocketState.CONNECTED)
    application_state = getattr(ws, "application_state", WebSocketState.CONNECTED)
    return (
        client_state == WebSocketState.CONNECTED
        and application_state == WebSocketState.CONNECTED
    )


async def _send_json_if_connected(
    ws: WebSocket,
    payload: dict[str, object],
) -> bool:
    """Send once, returning false only when the peer closed concurrently."""
    if not _websocket_is_connected(ws):
        return False
    try:
        await ws.send_json(payload)
        return True
    except RuntimeError:
        if not _websocket_is_connected(ws):
            return False
        raise
logger = logging.getLogger("streaming")

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"       # Nova-3 (v1)
DEEPGRAM_FLUX_WS_URL = "wss://api.deepgram.com/v2/listen"  # Flux (v2)
DEEPGRAM_API_KEY = voice_config.DEEPGRAM_API_KEY
MAIN_BACKEND_URL = os.getenv("NABLIX_MAIN_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")

# ---------------------------------------------------------------------------
# STT model selection
# ---------------------------------------------------------------------------
# "nova-3" -> legacy path: Deepgram v1 + our own silence timer / UtteranceEnd
#             turn detection.  This is what shipped before Flux.
# "flux"   -> Deepgram v2 with model-integrated turn detection.  Flux tells us
#             when a turn starts and ends, so all of our timer machinery is
#             bypassed.
#
# Defaults to nova-3 on purpose: pulling this code onto the VM without setting
# the env var must not silently change production behaviour.  Opt in with
# VOICE_STT_MODEL=flux.
STT_MODEL = os.getenv("VOICE_STT_MODEL", "nova-3").strip().lower()
USE_FLUX = STT_MODEL == "flux"

# Flux end-of-turn tuning.  See https://developers.deepgram.com/docs/flux/configuration
#   eot_threshold  (0.5-0.9, default 0.7): confidence needed to fire EndOfTurn.
#                  Higher = waits longer to be sure, fewer mid-sentence cutoffs.
#                  We default to 0.8 because students pause mid-thought while
#                  doing mental arithmetic and a false cutoff is worse for us
#                  than an extra ~100ms of latency.
#   eot_timeout_ms (500-60000, default 5000): hard ceiling on silence before a
#                  turn is forced closed regardless of confidence.
FLUX_EOT_THRESHOLD = float(os.getenv("VOICE_FLUX_EOT_THRESHOLD", "0.8"))
FLUX_EOT_TIMEOUT_MS = int(os.getenv("VOICE_FLUX_EOT_TIMEOUT_MS", "5000"))


class TurnState(str, Enum):
    """Explicit conversation state for the Flux path.

    The Nova-3 path tracked this implicitly across ~8 separate booleans and
    strings (is_processing, turn_already_processed, pending_transcript, ...)
    mutated from three concurrent coroutines with no locking.  That is where
    both of the August bugs lived.  Flux gives us real turn events, so the
    state becomes a single variable with explicit transitions.

        IDLE       no Deepgram connection / no audio flowing
        LISTENING  student is (or may be) speaking; Flux is accumulating
        PROCESSING backend tutor call is in flight
        SPEAKING   streaming TTS audio down to the frontend

    Only ONE turn task exists at a time.  If a new turn starts while a
    previous one is still PROCESSING or SPEAKING, the old task is cancelled
    outright -- the student has moved on, so its answer is stale by
    definition.  That single rule replaces the entire pending_transcript /
    cancel-and-reprocess buffer.
    """

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"

# Adaptive silence timeout (seconds).
# Instead of a single fixed timeout, we use different timeouts based on
# how many words the student has spoken so far.  Short utterances like
# "yes" or "hello" use a short timeout for quick responses.  Longer
# utterances (student mid-explanation) use a longer timeout so thinking
# pauses don't fragment the sentence.
SILENCE_SHORT_SECONDS = float(os.getenv("VOICE_SILENCE_SHORT_SECONDS", "3.0"))    # 1-3 words
SILENCE_MEDIUM_SECONDS = float(os.getenv("VOICE_SILENCE_MEDIUM_SECONDS", "5.0"))  # 4-6 words
SILENCE_LONG_SECONDS = float(os.getenv("VOICE_SILENCE_LONG_SECONDS", "12.5"))     # 7+ words

def _get_adaptive_timeout(transcript: str) -> float:
    """Return silence timeout based on word count of current buffer.

    Short utterances (1-3 words) -> 3.0s  (likely complete: "yes", "I don't know")
    Medium utterances (4-6 words) -> 5.0s (could be complete or mid-sentence)
    Long utterances (7+ words) -> 12.5s   (likely mid-explanation, give thinking room)
    """
    word_count = len(transcript.split())
    if word_count <= 3:
        return SILENCE_SHORT_SECONDS
    elif word_count <= 6:
        return SILENCE_MEDIUM_SECONDS
    else:
        return SILENCE_LONG_SECONDS

# Math-domain keyterms for Deepgram Nova-3 keyterm prompting.
# These help the STT model recognize math vocabulary that it
# often mis-transcribes (e.g. "coefficient" -> "co efficient",
# "x equals" -> "eggs equals"). Up to 100 terms / 500 tokens.
# Docs: https://developers.deepgram.com/docs/keyterm
MATH_KEYTERMS = [
    # Algebra basics
    "equation", "variable", "coefficient", "constant",
    "expression", "simplify", "substitute",
    # Operations
    "addition", "subtraction", "multiplication", "division",
    "subtract", "multiply", "divide",
    # Fractions and numbers
    "numerator", "denominator", "fraction", "decimal",
    "negative", "positive", "integer",
    # Equation solving
    "solve for x", "both sides", "isolate",
    "x equals", "inverse operation", "x equal to", "x is equal to", "x is",
    # Types
    "linear", "quadratic", "one step", "two step",
    # Common math phrases students say
    "plus", "minus", "times", "divided by", "equals",
    "squared", "cubed", "square root",
    "greater than", "less than",
]


def _build_deepgram_params(language: str = "en") -> str:
    """Build the Deepgram WebSocket query string with keyterm prompting."""
    params = (
        f"?model=nova-3"
        f"&language={language}"
        f"&smart_format=true"
        f"&punctuate=true"
        f"&interim_results=true"
        f"&endpointing=3500"
        f"&utterance_end_ms=5000"
        f"&encoding=linear16"
        f"&sample_rate=16000"
        f"&channels=1"
    )
    # Add each math keyterm. Multi-word phrases use + encoding.
    for term in MATH_KEYTERMS:
        encoded = term.replace(" ", "+")
        params += f"&keyterm={encoded}"
    return params


def _build_flux_params() -> str:
    """Build the Deepgram Flux (/v2/listen) WebSocket query string.

    Differences from the Nova-3 params above, all per Deepgram's docs:

      - model must be `flux-general-en`, not `nova-3`.
      - `language` must NOT be sent.  The docs list `language=en` as a
        common mistake with flux-general-en; language is implied by the
        model name.  (Only flux-general-multi accepts `language_hint`.)
      - `smart_format` and `punctuate` are unsupported by Flux and are
        dropped.  Transcripts come back unformatted, so numbers may arrive
        as words ("six" rather than "6").  normalize_math() already runs
        downstream and the LLM handles spoken numbers, so this is cosmetic.
      - `interim_results` is gone; Flux sends `Update` events instead.
      - `endpointing` / `utterance_end_ms` are gone; turn detection is in
        the model now, tuned via eot_threshold / eot_timeout_ms.
      - keyterm prompting IS supported and carries over unchanged, which
        matters -- it is what keeps "coefficient" from becoming
        "co efficient" and "x equals" from becoming "eggs equals".
    """
    params = (
        f"?model=flux-general-en"
        f"&encoding=linear16"
        f"&sample_rate={voice_config.STT_SAMPLE_RATE}"
        f"&eot_threshold={FLUX_EOT_THRESHOLD}"
        f"&eot_timeout_ms={FLUX_EOT_TIMEOUT_MS}"
    )
    for term in MATH_KEYTERMS:
        encoded = term.replace(" ", "+")
        params += f"&keyterm={encoded}"
    return params


def _flux_confidence(turn_info: dict) -> float:
    """Derive a transcript-level confidence from a Flux TurnInfo message.

    Nova-3 hands us a single `alternatives[0].confidence`.  Flux does not --
    it reports confidence per word.  The rest of the pipeline (and the
    frontend's `needs_clarification` flag) expects one number, so we average
    the word confidences.

    Returns 0.0 when there are no words, which is the same "unknown" value
    the Nova-3 path used.
    """
    words = turn_info.get("words") or []
    scores = [
        w.get("confidence")
        for w in words
        if isinstance(w, dict) and isinstance(w.get("confidence"), (int, float))
    ]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _stt_connection_config(language: str = "en") -> tuple[str, str]:
    """Return (websocket_url, human_readable_label) for the active STT model.

    Flux ignores `language` -- it is baked into the model name.  The
    parameter is accepted anyway so both connect paths can call this the
    same way regardless of which model is active.
    """
    if USE_FLUX:
        return DEEPGRAM_FLUX_WS_URL + _build_flux_params(), "Flux (v2)"
    return DEEPGRAM_WS_URL + _build_deepgram_params(language), "Nova-3 (v1)"

# Reuse one backend client, but create it lazily so importing app.main does not
# initialize the voice streaming HTTP stack.
_backend_http_client: httpx.AsyncClient | None = None


def get_backend_http_client() -> httpx.AsyncClient:
    global _backend_http_client

    if _backend_http_client is None:
        _backend_http_client = httpx.AsyncClient(
            base_url=MAIN_BACKEND_URL,
            timeout=15.0,
        )
    return _backend_http_client

MATH_NORMALIZATIONS = {
    "five over six": "5/6",
    "x equals five": "x = 5",
    "x equals six": "x = 6",
    "x equals four": "x = 4",
    "x equals seven": "x = 7",
    "x equals three": "x = 3",
    "two thirds plus one fourth": "2/3 + 1/4",
    "x squared plus three": "x^2 + 3",
}

def normalize_math(transcript: str) -> str | None:
    lower = transcript.lower().strip().rstrip(".")
    return MATH_NORMALIZATIONS.get(lower)


async def evaluate_voice_transcript(
    session_id: str,
    student_id: str,
    transcript: str,
    confidence: float,
    audio_duration_seconds: float,
    access_token: str,
    turn_id: str | None,
    previous_tutor_turn_id: str | None,
    transcript_final: bool | None,
    canvas_snapshot_id: str | None,
) -> dict[str, object]:
    if turn_id is None:
        raise ValueError("turn_id is required for voice interactions")
    if transcript_final is not True:
        raise ValueError("transcript_final must be true for voice interactions")
    payload = {
        "session_id": session_id,
        "student_id": student_id,
        "transcript": transcript,
        "confidence": confidence,
        "audio_duration_seconds": audio_duration_seconds,
        "turn": "STUDENT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "turn_id": turn_id,
        "previous_tutor_turn_id": previous_tutor_turn_id,
        "transcript_final": transcript_final,
        "canvas_snapshot_id": canvas_snapshot_id,
    }
    logger.info(f"[{session_id}] POST /voice/transcript")
    response = await get_backend_http_client().post(
        "/voice/transcript",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        # Same budget as /canvas/submit below. This call previously inherited
        # the client default of 15s while canvas got 40s for comparable LLM
        # work; slowest observed voice turn was 12.5s (30 Jul, n=121), which
        # left 17% headroom before a timeout indistinguishable from an outage.
        timeout=40.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"status={response.status_code} body={response.text}")
    return response.json()


async def submit_canvas_work(
    session_id: str,
    student_id: str,
    snapshot_data_url: str,
    transcript: str,
    confidence: float,
    access_token: str,
) -> dict[str, object]:
    payload = {
        "session_id": session_id,
        "student_id": student_id,
        "snapshot_data_url": snapshot_data_url,
        "transcript": transcript or None,
        "transcript_confidence": confidence,
        "submission_role": "VOICE_ATTACHMENT",
    }
    logger.info(f"[{session_id}] POST {MAIN_BACKEND_URL}/canvas/submit")
    response = await get_backend_http_client().post(
        "/canvas/submit",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=40.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"status={response.status_code} body={response.text}")
    return response.json()


def _canvas_draw_from(result: dict[str, object]) -> list[object]:
    canvas_draw = result.get("canvas_draw")
    if not isinstance(canvas_draw, list):
        raise RuntimeError("canvas response missing canvas_draw list")
    return canvas_draw


def _tts_retry_count() -> int:
    """Main-app adapter retry setting; default when running standalone."""
    try:
        from app.core.config import get_settings

        return get_settings().adapter_request_retry_count
    except Exception:
        return 2


async def synthesize_speech(
    text: str,
    provider: str | None = None,
    voice: str | None = None,
) -> str | None:
    """Configured TTS (OpenAI when keyed) → base64 mp3; None on empty text.

    *provider* and *voice* are optional per-request overrides sent by the
    frontend voice picker.  When ``None`` the process-level env defaults
    (``VOICE_TTS_PROVIDER`` / ``VOICE_TTS_VOICE``) are used, so existing
    callers that pass only ``text`` keep working unchanged.

    Retries provider failures per the adapter retry setting, then raises so the
    caller can return an explicit error (frontend falls back to browser speech).
    """
    if not text:
        return None
    use_provider = provider or voice_config.DEFAULT_TTS_PROVIDER
    use_voice = voice or voice_config.TTS_VOICE
    attempts = _tts_retry_count() + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            tts_adapter = get_tts_adapter(use_provider)
            result = await tts_adapter.generate_speech(
                text=text,
                voice=use_voice,
                audio_format="mp3",
            )
            audio_data = result.audio_data
            if isinstance(audio_data, str):
                audio_data = audio_data.encode("utf-8")
            return base64.b64encode(audio_data).decode("utf-8")
        except Exception as e:
            last_error = e
            logger.warning(f"TTS attempt {attempt}/{attempts} failed: {e}")
    raise RuntimeError(f"TTS failed after {attempts} attempts: {last_error}")

app = FastAPI(
    title="Nablix Math Tutor - Voice Streaming Server",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def warm_tts_connection():
    """Pre-warm the TTS adapter on server startup.

    The first TTS call is always slower because it needs to establish
    a new HTTPS connection to OpenAI (~300-500ms overhead).  By making
    a tiny dummy call at startup, the connection pool is warm and
    ready when the first real student request arrives.
    """
    try:
        tts_adapter = get_tts_adapter(voice_config.DEFAULT_TTS_PROVIDER)
        await tts_adapter.generate_speech(text="hello", voice=voice_config.TTS_VOICE, audio_format="mp3")
        logger.info("TTS connection pre-warmed successfully")
    except Exception as e:
        logger.warning(f"TTS pre-warm failed (non-fatal): {e}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "voice-streaming"}

@app.websocket("/voice/stream")
async def voice_stream(
    ws: WebSocket,
    session: str = "default",
    student_id: str = "ST001",
    tts_provider: str | None = None,
    tts_voice: str | None = None,
):
    session_id = session  # frontend sends ?session=, not ?session_id=
    await ws.accept()
    logger.info(f"[{session_id}] WebSocket connected (tts_provider={tts_provider}, tts_voice={tts_voice})")

    language = "en"
    deepgram_ws = None
    final_transcript = ""
    final_confidence = 0.0
    final_segment_count = 0
    receiving_audio = False
    audio_started_at = 0.0
    turn_already_processed = False  # True when UtteranceEnd auto-triggered a response
    last_transcript_at = time.time()  # when Deepgram last sent a transcript
    is_processing = False  # True while process_and_respond is running (Tier 2)
    pending_transcript = ""  # Speech that arrived during processing (Tier 2)
    pending_confidence = 0.0
    access_token: str | None = None
    turn_id: str | None = None
    previous_tutor_turn_id: str | None = None
    transcript_final: bool | None = None

    # --- Flux path state (unused when STT_MODEL=nova-3) ---
    # One variable instead of the five booleans above, and exactly one
    # in-flight turn task at a time.
    turn_state = TurnState.IDLE
    active_turn_task: asyncio.Task | None = None

    # Latest canvas snapshot seen on ANY inbound message, awaiting a turn to
    # attach to.  On the Nova-3 path the snapshot rides in on `stop` and is
    # consumed by the turn processed in that same handler.  Flux ends turns
    # on its own schedule, so there is no `stop` to hang it off -- we latch
    # the most recent snapshot instead and attach it to the next turn, then
    # clear it so it is never applied twice.
    pending_canvas_snapshot: str | None = None

    # Last turn_id actually dispatched to the backend, so a reused one can
    # be called out in the logs.
    last_dispatched_turn_id: str | None = None

    def _note_dispatched_turn(dispatched: str | None) -> None:
        nonlocal last_dispatched_turn_id
        last_dispatched_turn_id = dispatched

    async def deepgram_keepalive() -> None:
        # Deepgram closes a stream that receives neither audio nor text for
        # ~10s (NET-0001). That happens on every mute, because the frontend
        # stops sending chunks while muted — 8 such kills in the 30-31 Jul
        # logs, each costing the student an utterance mid-conversation.
        # The documented fix is a KeepAlive text frame; it is harmless while
        # audio is flowing and resets the idle timer while it is not.
        # https://developers.deepgram.com/docs/keep-alive
        #
        # Flux does NOT use this. Per the Flux/Nova-3 comparison, v2 replaces
        # the KeepAlive text frame with WebSocket protocol pings and a 60s
        # (not 12s) idle timeout. The `websockets` client already sends PING
        # frames every 20s by default, so the connection is held open for us.
        # `KeepAlive` is not a documented Flux control message -- only
        # CloseStream and Configure are -- so sending it would at best be
        # ignored and at worst draw an error frame.
        if USE_FLUX:
            return

        while True:
            await asyncio.sleep(5)
            ws_now = deepgram_ws
            if ws_now is None:
                continue
            try:
                await ws_now.send(json.dumps({"type": "KeepAlive"}))
            except Exception:
                # Closed or resetting mid-send; the reconnect paths own recovery.
                pass

    keepalive_task = asyncio.create_task(deepgram_keepalive())

    deepgram_receiver_task = None
    silence_timer_task = None

    # Background tasks set — prevents garbage collection of fire-and-forget
    # tasks (V-1 fix: process_and_respond runs as a background task instead
    # of blocking the Deepgram receiver loop).
    _background_tasks: set[asyncio.Task] = set()

    async def _process_buffer():
        """Process whatever is in the final_transcript buffer.

        Called by:
          - speech_final (primary: Deepgram VAD detected end of speech)
          - UtteranceEnd (backup: transcript word-timing gap detected)
          - silence fallback timer (last resort: no messages for N seconds)

        Tier 2 (cancel-and-reprocess): If new speech arrives WHILE this
        function is running (is_processing=True), the receiver stores it
        in pending_transcript.  When this function finishes, it checks
        for pending speech and processes it automatically.
        """
        nonlocal final_transcript, final_confidence, final_segment_count
        nonlocal audio_started_at, turn_already_processed
        nonlocal turn_id, previous_tutor_turn_id, transcript_final
        nonlocal silence_timer_task, is_processing
        nonlocal pending_transcript, pending_confidence

        if not final_transcript:
            return

        is_processing = True
        transcript_to_process = final_transcript
        confidence_to_process = final_confidence
        duration = max(time.time() - audio_started_at, 0.001)

        # Reset buffer for potential next utterance
        final_transcript = ""
        final_confidence = 0.0
        final_segment_count = 0
        audio_started_at = time.time()
        turn_already_processed = True

        try:
            if access_token is None:
                await ws.close(code=4401, reason="Authentication required")
                return
            await process_and_respond(
                ws, session_id, student_id,
                transcript_to_process, confidence_to_process,
                duration, access_token, None,
                tts_provider, tts_voice,
                turn_id, previous_tutor_turn_id, transcript_final,
            )
        except Exception as e:
            turn_already_processed = False
            logger.error(f"[{session_id}] _process_buffer failed: {e}")
        finally:
            is_processing = False
            # NOTE: Do NOT clear turn_id, previous_tutor_turn_id,
            # or transcript_final here.  The frontend sends these
            # once per turn via turn_context messages.  If we clear
            # them after the first fragment, any pending speech that
            # gets processed next will fail with "turn_id is required"
            # because the frontend won't re-send them.
            silence_timer_task = None

            # Tier 2: Check if speech arrived while we were processing.
            # If so, move it into the main buffer and process again.
            if pending_transcript:
                logger.info(
                    f"[{session_id}] Pending speech from during processing: "
                    f"'{pending_transcript}' - moving to buffer"
                )
                final_transcript = pending_transcript
                final_confidence = pending_confidence
                final_segment_count = 1
                pending_transcript = ""
                pending_confidence = 0.0
                # Start a new silence timer for the pending speech.
                # Don't process immediately -- give the student time
                # to continue speaking.
                silence_timer_task = asyncio.create_task(
                    _silence_fallback_handler()
                )

    async def _silence_fallback_handler():
        """Last-resort fallback when neither speech_final nor UtteranceEnd fire.

        Uses adaptive timeout based on word count:
          1-3 words  -> 3.0s  (short utterance, likely complete)
          4-6 words  -> 5.0s  (medium, could go either way)
          7+ words   -> 12.5s (long, student probably thinking mid-sentence)

        DEBOUNCE LOOP: instead of a flat asyncio.sleep(timeout), this
        loops and re-checks how much time has passed since the last
        Deepgram message (partial OR final).  If new messages arrived
        (meaning the student is still speaking), last_transcript_at
        will have been updated, and the timer keeps waiting.  Only
        when truly no Deepgram messages arrive for the full timeout
        period does it process the buffer.

        This prevents the bug where FINAL "So see." starts a 3s timer,
        but partials "I believe on the left..." arrive during the sleep
        and the timer fires anyway (actual gap 0.7s).
        """
        nonlocal silence_timer_task

        while True:
            # Recalculate timeout from current buffer (may have
            # grown since the timer started if new FINALs arrived).
            timeout = (
                _get_adaptive_timeout(final_transcript)
                if final_transcript
                else SILENCE_LONG_SECONDS
            )
            elapsed = time.time() - last_transcript_at
            remaining = timeout - elapsed

            if remaining <= 0:
                # Full timeout elapsed with no new messages.
                break

            await asyncio.sleep(remaining)

        if not final_transcript:
            return

        actual_gap = round(time.time() - last_transcript_at, 1)
        timeout = _get_adaptive_timeout(final_transcript)
        logger.info(
            f"[{session_id}] Silence fallback (adaptive {timeout}s, "
            f"{len(final_transcript.split())} words) - "
            f"actual gap {actual_gap}s - "
            f"auto-processing: '{final_transcript}'"
        )
        await _process_buffer()

    # ------------------------------------------------------------------
    # Flux path (STT_MODEL=flux)
    # ------------------------------------------------------------------

    async def _cancel_active_turn(
        reason: str,
        notify_frontend: bool,
        expect_new_turn: bool = False,
    ) -> None:
        """Cancel the in-flight turn task, if there is one.

        `notify_frontend=True` also emits tutor_audio_cancel so the client
        can stop playback mid-sentence.  We only do that for barge-in --
        when a turn is merely superseded there was nothing audible yet.

        `expect_new_turn` is carried on that message and tells the frontend
        whether it must open a NEW student turn (mint a turn_id and re-send
        turn_context) before the next transcript arrives.

        This has to be explicit rather than something the client infers from
        `reason`, because the two cases genuinely differ:

          barge_in            -> True.  The student is speaking right now and
                                 the tutor audio never reaches idle, so the
                                 frontend's normal "audio finished, open next
                                 turn" trigger never fires.  Without a new
                                 turn_id the barged-in turn would arrive
                                 carrying the previous turn's context and the
                                 backend would reject it as stale.
          superseded_by_text  -> False. The text path has already opened its
                                 own turn; minting another would clobber the
                                 id the answer was submitted under.

        Encoding this server-side means adding a future reason does not
        require the frontend to learn its turn semantics.
        """
        nonlocal active_turn_task

        task = active_turn_task
        active_turn_task = None
        if task is None or task.done():
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"[{session_id}] Error awaiting cancelled turn: {exc}")

        logger.info(f"[{session_id}] Cancelled in-flight turn ({reason})")

        if notify_frontend:
            try:
                await ws.send_json({
                    "type": "tutor_audio_cancel",
                    "reason": reason,
                    "expect_new_turn": expect_new_turn,
                })
            except Exception:
                # Client already gone; nothing to stop.
                pass

    async def _run_turn(
        transcript: str, confidence: float, duration: float
    ) -> None:
        """Own the state transitions around one call to process_and_respond."""
        nonlocal turn_state, pending_canvas_snapshot

        def _mark_speaking() -> None:
            nonlocal turn_state
            turn_state = TurnState.SPEAKING

        # Consume any latched canvas snapshot so it is attached exactly once.
        canvas_snapshot = pending_canvas_snapshot
        pending_canvas_snapshot = None
        if canvas_snapshot:
            logger.info(
                f"[{session_id}] Attaching pending canvas snapshot to turn"
            )

        turn_state = TurnState.PROCESSING
        try:
            if access_token is None:
                await ws.close(code=4401, reason="Authentication required")
                return

            # Validate turn context BEFORE calling the backend.
            #
            # evaluate_voice_transcript raises ValueError when turn_id is
            # missing or transcript_final is not True.  Inside a background
            # task that surfaces as a one-line "Turn failed" with no clue
            # which field was wrong -- which is how voice-logs-15 line 77
            # read.  Flux makes this far more likely than Nova-3 did: it
            # detects several turns per connection with no `stop` between
            # them, so a frontend that mints turn context once per *session*
            # rather than once per *turn* will fail from turn two onward.
            missing = []
            if turn_id is None:
                missing.append("turn_id")
            if transcript_final is not True:
                missing.append("transcript_final")
            if missing:
                logger.error(
                    f"[{session_id}] Skipping backend call for turn "
                    f"'{transcript}': frontend did not supply "
                    f"{' and '.join(missing)} over the WebSocket. "
                    f"Flux needs these re-sent for EVERY turn, not once "
                    f"per session."
                )
                await ws.send_json({
                    "type": "error",
                    "message": "Tutor unavailable. Please try again.",
                    "fallback_mode": "TEXT",
                })
                return

            # Reuse is not fatal -- the backend owns stale-turn dedupe via
            # previous_tutor_turn_id -- but it is almost always the bug
            # above, so say so loudly rather than silently letting the
            # backend reject it.
            if turn_id == last_dispatched_turn_id:
                logger.warning(
                    f"[{session_id}] turn_id '{turn_id}' reused for a second "
                    f"turn ('{transcript}'). The backend will likely reject "
                    f"this as stale. Frontend should mint a new turn_id per "
                    f"turn."
                )
            _note_dispatched_turn(turn_id)

            await process_and_respond(
                ws, session_id, student_id,
                transcript, confidence,
                duration, access_token, canvas_snapshot,
                tts_provider, tts_voice,
                turn_id, previous_tutor_turn_id, transcript_final,
                on_audio_start=_mark_speaking,
            )
        except asyncio.CancelledError:
            # Barge-in or superseded turn. Expected, not an error.
            raise
        except Exception as exc:
            logger.error(f"[{session_id}] Turn failed: {exc}")
        finally:
            # Whatever happened, we are ready to hear the student again.
            turn_state = TurnState.LISTENING

    async def _forward_flux_results(dg_ws):
        """Drive the conversation off Flux's turn events.

        Replaces the entire speech_final / UtteranceEnd / adaptive-silence-
        timer stack.  There is no timer here at all: Flux decides when a
        turn ends, and we act on that decision.
        """
        nonlocal turn_state, active_turn_task, audio_started_at

        try:
            async for msg in dg_ws:
                data = json.loads(msg)
                msg_type = data.get("type")

                if msg_type != "TurnInfo":
                    # Connected / Error / Fatal and friends.
                    logger.info(f"[{session_id}] Flux message: {msg_type} {data}")
                    continue

                event = data.get("event")
                transcript = (data.get("transcript") or "").strip()
                turn_index = data.get("turn_index")

                if event == "StartOfTurn":
                    # Student started speaking.  If the tutor is mid-answer,
                    # that is a barge-in: kill the answer and listen.
                    if turn_state in (TurnState.PROCESSING, TurnState.SPEAKING):
                        await _cancel_active_turn(
                            "barge_in",
                            notify_frontend=True,
                            expect_new_turn=True,
                        )
                    turn_state = TurnState.LISTENING
                    audio_started_at = time.time()
                    logger.info(
                        f"[{session_id}] Flux StartOfTurn (turn {turn_index})"
                    )

                elif event == "Update":
                    # Interim transcript. Emitted on the same wire message
                    # the frontend already handles, so no client change.
                    if transcript:
                        await ws.send_json({
                            "type": "transcript_partial",
                            "text": transcript,
                            "confidence": round(_flux_confidence(data), 4),
                            "is_final": False,
                            "role": "student",
                        })

                elif event == "EndOfTurn":
                    if not transcript:
                        logger.info(
                            f"[{session_id}] Flux EndOfTurn with empty "
                            f"transcript (turn {turn_index}) - ignoring"
                        )
                        continue

                    confidence = _flux_confidence(data)
                    eot_confidence = data.get("end_of_turn_confidence", 0.0)

                    await ws.send_json({
                        "type": "transcript_final",
                        "text": transcript,
                        "confidence": round(confidence, 4),
                        "is_final": True,
                        "role": "student",
                    })

                    logger.info(
                        f"[{session_id}] Flux EndOfTurn (turn {turn_index}, "
                        f"eot_conf={eot_confidence:.3f}, "
                        f"word_conf={confidence:.4f}): '{transcript}'"
                    )

                    # Anything still running belongs to an older turn.
                    await _cancel_active_turn("superseded", notify_frontend=False)

                    duration = max(time.time() - audio_started_at, 0.001)
                    active_turn_task = asyncio.create_task(
                        _run_turn(transcript, confidence, duration)
                    )
                    _background_tasks.add(active_turn_task)
                    active_turn_task.add_done_callback(_background_tasks.discard)

                elif event in ("EagerEndOfTurn", "TurnResumed"):
                    # We do not set eager_eot_threshold, so these should not
                    # arrive. Log rather than swallow if they ever do.
                    logger.info(
                        f"[{session_id}] Flux {event} received "
                        f"(eager mode not enabled) - ignoring"
                    )

                else:
                    logger.info(
                        f"[{session_id}] Flux unhandled TurnInfo event: {event}"
                    )

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[{session_id}] Flux connection closed")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[{session_id}] Flux receiver error: {e}")

    # ------------------------------------------------------------------
    # Nova-3 path (STT_MODEL=nova-3) -- legacy, timer-driven
    # ------------------------------------------------------------------

    async def forward_deepgram_results(dg_ws):
        nonlocal final_transcript, final_confidence, final_segment_count, audio_started_at, turn_already_processed
        nonlocal turn_id, previous_tutor_turn_id, transcript_final
        nonlocal silence_timer_task, last_transcript_at
        nonlocal pending_transcript, pending_confidence

        try:
            async for msg in dg_ws:
                data = json.loads(msg)
                msg_type = data.get("type", "unknown")

                # Debug: log every Deepgram message type so we can
                # check whether UtteranceEnd is actually being sent.
                if msg_type != "Results":
                    logger.info(
                        f"[{session_id}] Deepgram event: {msg_type}"
                    )

                if msg_type == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])

                    if not alternatives:
                        continue

                    best = alternatives[0]
                    transcript = best.get("transcript", "").strip()
                    confidence = best.get("confidence", 0.0)
                    is_final = data.get("is_final", False)
                    # speech_final is Deepgram's VAD-based endpointing signal.
                    # It fires after `endpointing` ms of actual audio silence
                    # (detected by Voice Activity Detection on the raw audio,
                    # NOT transcript timing).  This is our PRIMARY signal that
                    # the student has stopped speaking.
                    speech_final = data.get("speech_final", False)

                    if not transcript:
                        continue

                    if is_final:
                        # Tier 2: If we're currently processing a previous
                        # turn, store new speech in the pending buffer.
                        # It will be picked up after processing finishes.
                        if is_processing:
                            if pending_transcript:
                                pending_transcript += " " + transcript
                            else:
                                pending_transcript = transcript
                            pending_confidence = confidence
                            logger.info(
                                f"[{session_id}] Speech during processing, "
                                f"queued: '{pending_transcript}'"
                            )
                        else:
                            if final_transcript:
                                final_transcript += " " + transcript
                            else:
                                final_transcript = transcript
                            # Track a running average confidence across all
                            # final segments instead of just keeping the last
                            final_segment_count += 1
                            final_confidence = (
                                (final_confidence * (final_segment_count - 1) + confidence)
                                / final_segment_count
                            )

                    # Guarded: this runs in a background task, so an
                    # unguarded send-after-close raises RuntimeError, escapes
                    # the `async for`, and is swallowed by the `except
                    # Exception` at the bottom of this function -- killing the
                    # receiver outright.  The session would keep its socket
                    # and keep feeding audio to Deepgram while silently
                    # producing no further transcripts, with one log line as
                    # the only evidence.  This send fires every few hundred ms
                    # for as long as the student is talking, so it has the
                    # widest exposure of any send in the file.
                    delivered = await _send_json_if_connected(ws, {
                        "type": "transcript_partial" if not is_final else "transcript_final",
                        "text": transcript,
                        "confidence": round(confidence, 4),
                        "is_final": is_final,
                        "role": "student",
                    })
                    if not delivered:
                        logger.info(
                            f"[{session_id}] Client closed mid-speech - "
                            f"stopping Deepgram receiver"
                        )
                        return

                    last_transcript_at = time.time()

                    logger.info(
                        f"[{session_id}] {'FINAL' if is_final else 'partial'}"
                        f"{'(speech_final)' if speech_final else ''}: "
                        f"'{transcript}' (conf={confidence:.4f})"
                    )

                    # --- Turn processing logic ---
                    #
                    # PRIMARY signal: speech_final=true from Deepgram's VAD.
                    #   Deepgram's endpointing (3500ms) detected real audio
                    #   silence.  Process the buffer immediately.
                    #
                    # FALLBACK signal: silence timer (adaptive timeout).
                    #   If speech_final never fires (noisy environment, or
                    #   Deepgram VAD fails), our timer processes the buffer
                    #   after N seconds of no transcript messages.
                    #
                    if speech_final and final_transcript:
                        # Deepgram's VAD confirms the student stopped speaking.
                        # Cancel any pending silence timer and process now.
                        if silence_timer_task and not silence_timer_task.done():
                            silence_timer_task.cancel()
                            silence_timer_task = None
                        logger.info(
                            f"[{session_id}] speech_final triggered - "
                            f"processing: '{final_transcript}'"
                        )
                        await _process_buffer()
                    elif is_final and final_transcript:
                        # is_final but NOT speech_final: Deepgram finalized a
                        # segment (happens every ~3-5s) but the student may
                        # still be talking.  Start/reset the fallback timer.
                        if silence_timer_task and not silence_timer_task.done():
                            silence_timer_task.cancel()
                        silence_timer_task = asyncio.create_task(
                            _silence_fallback_handler()
                        )

                elif data.get("type") == "UtteranceEnd":
                    # UtteranceEnd fires after utterance_end_ms (5000ms) of
                    # no new words in transcripts.  It's a BACKUP for noisy
                    # environments where speech_final might not fire.
                    # If there's still content in the buffer, process it.
                    if final_transcript:
                        if silence_timer_task and not silence_timer_task.done():
                            silence_timer_task.cancel()
                            silence_timer_task = None
                        logger.info(
                            f"[{session_id}] UtteranceEnd triggered (backup) - "
                            f"processing: '{final_transcript}'"
                        )
                        await _process_buffer()
                    else:
                        logger.info(
                            f"[{session_id}] UtteranceEnd received "
                            f"(buffer empty, nothing to process)"
                        )

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[{session_id}] Deepgram connection closed")
        except Exception as e:
            logger.error(f"[{session_id}] Deepgram receiver error: {e}")

    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type", "")
                if "turn_id" in data:
                    turn_id = data.get("turn_id")
                if "previous_tutor_turn_id" in data:
                    previous_tutor_turn_id = data.get("previous_tutor_turn_id")
                if "transcript_final" in data:
                    transcript_final = data.get("transcript_final")

                # Latch a canvas snapshot from whichever message carries it.
                #
                # Two field names are in play: the `stop` message uses
                # `canvas_snapshot`, while the frontend's canvas_submission
                # message uses `png` (see useWebSocket.ts sendCanvasSubmission).
                # Accept either.
                #
                # This latch is additive for Nova-3: its `stop` handler still
                # prefers data["canvas_snapshot"] exactly as before, and only
                # falls back to the latch when stop carried no snapshot --
                # a case that previously meant "no canvas at all".
                snapshot_in = data.get("canvas_snapshot") or data.get("png")
                if snapshot_in:
                    pending_canvas_snapshot = snapshot_in
                    logger.info(
                        f"[{session_id}] Canvas snapshot latched from "
                        f"'{msg_type}' message"
                    )

                if msg_type == "authenticate":
                    candidate = data.get("access_token")
                    if not isinstance(candidate, str) or candidate == "":
                        await ws.close(code=4401, reason="Authentication required")
                        return
                    access_token = candidate
                    # No early return needed: this runs in the main receive
                    # loop, so if the client has gone the next ws.receive()
                    # yields websocket.disconnect and we break normally.
                    await _send_json_if_connected(
                        ws, {"type": "status", "message": "authenticated"}
                    )

                elif access_token is None:
                    await ws.close(code=4401, reason="Authenticate before sending data")
                    return

                elif msg_type == "start":
                    # Explicit start (optional -- audio_chunk auto-connects too).
                    # Clean up any existing Deepgram connection first to avoid
                    # duplicate connections from React re-renders.
                    if deepgram_ws:
                        try:
                            await deepgram_ws.close()
                        except Exception:
                            pass
                        deepgram_ws = None
                    if deepgram_receiver_task and not deepgram_receiver_task.done():
                        deepgram_receiver_task.cancel()
                        try:
                            await deepgram_receiver_task
                        except (asyncio.CancelledError, Exception):
                            pass

                    language = data.get("language", "en")
                    final_transcript = ""
                    final_confidence = 0.0
                    final_segment_count = 0
                    receiving_audio = True
                    audio_started_at = time.time()
                    turn_already_processed = False

                    turn_state = TurnState.LISTENING

                    dg_url, model_label = _stt_connection_config(language)
                    extra_headers = {
                        "Authorization": f"Token {DEEPGRAM_API_KEY}"
                    }

                    logger.info(
                        f"[{session_id}] Connecting to Deepgram {model_label}..."
                    )

                    ssl_context = ssl.create_default_context(cafile=certifi.where())

                    deepgram_ws = await websockets.connect(
                        dg_url,
                        additional_headers=extra_headers,
                        ssl=ssl_context,
                    )

                    logger.info(
                        f"[{session_id}] Deepgram {model_label} connected. "
                        f"Streaming started."
                    )

                    deepgram_receiver_task = asyncio.create_task(
                        _forward_flux_results(deepgram_ws)
                        if USE_FLUX
                        else forward_deepgram_results(deepgram_ws)
                    )

                    # Deepgram's connect above takes 100-300ms, which is long
                    # enough for a client to disappear before this lands.
                    await _send_json_if_connected(ws, {
                        "type": "status",
                        "message": "streaming_started",
                    })

                elif msg_type == "stop":
                    receiving_audio = False
                    # Cancel silence fallback -- explicit stop takes over
                    if silence_timer_task and not silence_timer_task.done():
                        silence_timer_task.cancel()
                        silence_timer_task = None
                    # Prefer the snapshot on the stop message itself (original
                    # behaviour); fall back to one latched from an earlier
                    # canvas_submission, which previously would have been lost.
                    canvas_snapshot = (
                        data.get("canvas_snapshot") or pending_canvas_snapshot
                    )
                    pending_canvas_snapshot = None
                    logger.info(f"[{session_id}] Stop received. Finalizing...")

                    if USE_FLUX:
                        # Under Flux, "stop" is the student muting the mic --
                        # it is NOT a turn boundary.  Flux owns turn detection
                        # and will emit a final EndOfTurn in response to
                        # CloseStream below, which _forward_flux_results
                        # handles like any other turn.  Processing a buffer
                        # here as well would double-send the turn.
                        if deepgram_ws:
                            try:
                                await deepgram_ws.send(
                                    json.dumps({"type": "CloseStream"})
                                )
                            except Exception:
                                pass
                            if deepgram_receiver_task:
                                try:
                                    await asyncio.wait_for(
                                        deepgram_receiver_task, timeout=10.0
                                    )
                                except asyncio.TimeoutError:
                                    logger.warning(
                                        f"[{session_id}] Flux receiver timed out"
                                    )
                                    deepgram_receiver_task.cancel()
                                    try:
                                        await deepgram_receiver_task
                                    except asyncio.CancelledError:
                                        pass
                            try:
                                await deepgram_ws.close()
                            except Exception:
                                pass
                            deepgram_ws = None
                        turn_state = TurnState.IDLE
                        # A turn spawned by the final EndOfTurn is still
                        # running in _background_tasks; let it finish.
                        continue

                    if deepgram_ws:
                        try:
                            await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                        except Exception:
                            pass

                        if deepgram_receiver_task:
                            dg_wait_start = time.time()
                            try:
                                await asyncio.wait_for(deepgram_receiver_task, timeout=10.0)
                            except asyncio.TimeoutError:
                                logger.warning(f"[{session_id}] Deepgram receiver timed out")
                                deepgram_receiver_task.cancel()
                                try:
                                    await deepgram_receiver_task
                                except asyncio.CancelledError:
                                    pass
                            dg_wait_ms = int((time.time() - dg_wait_start) * 1000)
                            logger.info(f"[{session_id}] Deepgram finalization took {dg_wait_ms}ms")

                        try:
                            await deepgram_ws.close()
                        except Exception:
                            pass
                        deepgram_ws = None

                    if final_transcript:
                        logger.info(f"[{session_id}] Processing on stop: '{final_transcript}'")
                        audio_duration_seconds = max(time.time() - audio_started_at, 0.001)
                        try:
                            await process_and_respond(
                                ws, session_id, student_id, final_transcript,
                                final_confidence, audio_duration_seconds, access_token, canvas_snapshot,
                                tts_provider, tts_voice,
                                turn_id, previous_tutor_turn_id, transcript_final,
                            )
                        except Exception as e:
                            logger.error(f"[{session_id}] Stop-path process failed: {e}")
                        finally:
                            turn_id = None
                            previous_tutor_turn_id = None
                            transcript_final = None
                    elif not turn_already_processed:
                        logger.info(f"[{session_id}] Stop: no speech detected")

                elif msg_type == "canvas_submission":
                    # The frontend has sent this since June (useWebSocket.ts
                    # sendCanvasSubmission) and the server had no handler, so
                    # every canvas submission over the socket was silently
                    # dropped.  The snapshot was already latched above; this
                    # branch exists so the message is acknowledged rather
                    # than falling through to the unknown-type warning.
                    stroke_count = len(data.get("strokes") or [])
                    logger.info(
                        f"[{session_id}] canvas_submission received "
                        f"({stroke_count} strokes) - snapshot latched for "
                        f"the next turn"
                    )
                    await ws.send_json({
                        "type": "status",
                        "message": "canvas_received",
                    })

                elif msg_type == "text_message":
                    # Typed student input. Same tutor path as a spoken turn,
                    # just with no STT in front of it -- confidence is 1.0
                    # because there is nothing to mis-hear.  Also previously
                    # unhandled and silently dropped.
                    text_input = (data.get("text") or "").strip()
                    if not text_input:
                        continue

                    logger.info(
                        f"[{session_id}] text_message received: '{text_input}'"
                    )

                    # A typed message supersedes anything still in flight,
                    # exactly like a new spoken turn does.
                    if USE_FLUX:
                        await _cancel_active_turn(
                            "superseded_by_text",
                            notify_frontend=True,
                            expect_new_turn=False,
                        )

                    snapshot_for_text = pending_canvas_snapshot
                    pending_canvas_snapshot = None
                    try:
                        await process_and_respond(
                            ws, session_id, student_id,
                            text_input, 1.0,
                            0.001, access_token, snapshot_for_text,
                            tts_provider, tts_voice,
                            turn_id, previous_tutor_turn_id, transcript_final,
                        )
                    except Exception as e:
                        logger.error(
                            f"[{session_id}] text_message processing failed: {e}"
                        )

                elif msg_type == "audio_chunk":
                    # Frontend sends base64-encoded PCM audio as JSON.
                    # Auto-connect to Deepgram on the first chunk -- no
                    # explicit "start" message needed.
                    audio_b64 = data.get("data", "")
                    if not audio_b64:
                        continue

                    # Auto-connect to Deepgram if not already connected
                    if deepgram_ws is None:
                        logger.info(f"[{session_id}] Auto-connecting to Deepgram (first audio chunk)...")

                        # Clean up stale receiver task if any
                        if deepgram_receiver_task and not deepgram_receiver_task.done():
                            deepgram_receiver_task.cancel()
                            try:
                                await deepgram_receiver_task
                            except (asyncio.CancelledError, Exception):
                                pass

                        final_transcript = ""
                        final_confidence = 0.0
                        final_segment_count = 0
                        turn_already_processed = False
                        receiving_audio = True
                        audio_started_at = time.time()
                        turn_state = TurnState.LISTENING

                        dg_url, model_label = _stt_connection_config(language)
                        extra_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
                        ssl_context = ssl.create_default_context(cafile=certifi.where())

                        try:
                            deepgram_ws = await websockets.connect(
                                dg_url,
                                additional_headers=extra_headers,
                                ssl=ssl_context,
                            )
                            deepgram_receiver_task = asyncio.create_task(
                                _forward_flux_results(deepgram_ws)
                                if USE_FLUX
                                else forward_deepgram_results(deepgram_ws)
                            )
                            logger.info(
                                f"[{session_id}] Deepgram {model_label} "
                                f"auto-connected."
                            )
                        except Exception as e:
                            logger.error(f"[{session_id}] Deepgram auto-connect failed: {e}")
                            deepgram_ws = None
                            continue

                    # Forward decoded audio to Deepgram
                    try:
                        audio_bytes = base64.b64decode(audio_b64)
                        await deepgram_ws.send(audio_bytes)
                    except Exception as e:
                        logger.error(f"[{session_id}] Failed to forward audio_chunk: {e}")
                        # Connection may have died, reset so next chunk reconnects
                        deepgram_ws = None

            elif "bytes" in message:
                if receiving_audio and deepgram_ws:
                    try:
                        await deepgram_ws.send(message["bytes"])
                    except Exception as e:
                        logger.error(f"[{session_id}] Failed to forward audio: {e}")

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Client disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] Error: {e}")
    finally:
        keepalive_task.cancel()
        if deepgram_receiver_task and not deepgram_receiver_task.done():
            deepgram_receiver_task.cancel()
        # Cancel any background process_and_respond tasks still running
        for bg_task in _background_tasks:
            if not bg_task.done():
                bg_task.cancel()
        _background_tasks.clear()
        if deepgram_ws:
            try:
                await deepgram_ws.close()
            except Exception:
                pass
        logger.info(f"[{session_id}] Session ended")

async def process_and_respond(
    ws: WebSocket,
    session_id: str,
    student_id: str,
    transcript: str,
    confidence: float,
    audio_duration_seconds: float,
    access_token: str,
    canvas_snapshot: str | None,
    tts_provider: str | None,
    tts_voice: str | None,
    turn_id: str | None,
    previous_tutor_turn_id: str | None,
    transcript_final: bool | None,
    on_audio_start=None,
):
    """Run one student turn through the tutor backend and stream the reply.

    `on_audio_start` is an optional zero-arg callback fired just before TTS
    audio starts streaming.  The Flux path uses it to move its state machine
    from PROCESSING to SPEAKING so barge-in knows there is audible output to
    interrupt.  Defaults to None so the existing callers and tests, which
    pass 13 positional arguments, are unaffected.
    """
    pipeline_start = time.time()

    normalized = normalize_math(transcript)
    if normalized:
        logger.info(f"[{session_id}] Normalized: '{transcript}' -> '{normalized}'")

    try:
        tutor_start = time.time()
        canvas_draw: list[object] = []
        if canvas_snapshot:
            canvas_response = await submit_canvas_work(
                session_id,
                student_id,
                canvas_snapshot,
                transcript,
                confidence,
                access_token,
            )
            canvas_draw = _canvas_draw_from(canvas_response)
            canvas_snapshot_id = str(canvas_response["submission_id"])
        else:
            canvas_snapshot_id = None
        tutor_response = await evaluate_voice_transcript(
            session_id,
            student_id,
            transcript,
            confidence,
            audio_duration_seconds,
            access_token,
            turn_id,
            previous_tutor_turn_id,
            transcript_final,
            canvas_snapshot_id,
        )
        tutor_ms = int((time.time() - tutor_start) * 1000)
        logger.info(f"[{session_id}] Backend tutor call took {tutor_ms}ms")
    except Exception as e:
        logger.error(f"[{session_id}] Main backend tutor call failed: {e}")
        await _send_json_if_connected(ws, {
            "type": "error",
            "message": "Tutor unavailable. Please try again.",
            "fallback_mode": "TEXT",
        })
        return

    tutor_text = str(tutor_response.get("message") or "")
    tutor_voice_text = str(tutor_response.get("message_voice") or tutor_text)

    # ---- Step 1: Send text response IMMEDIATELY ----
    # The frontend can display the text while audio streams in.
    # NOTE: audio_base64 is NOT included here anymore.
    text_sent_ms = int((time.time() - pipeline_start) * 1000)

    text_sent = await _send_json_if_connected(ws, {
        **tutor_response,
        "type": "tutor_response",
        "transcript": transcript,
        "normalized_expression": normalized,
        "confidence": round(confidence, 4),
        "text": tutor_text,
        "voice_text": tutor_voice_text,
        "needs_clarification": confidence < voice_config.CONFIDENCE_THRESHOLD,
        "text_latency_ms": text_sent_ms,
        "canvas_draw": canvas_draw,
    })
    if not text_sent:
        logger.info(f"[{session_id}] Client closed before tutor response delivery")
        return

    logger.info(f"[{session_id}] Text sent to frontend: {text_sent_ms}ms")

    # ---- Step 2: Stream TTS audio in chunks ----
    # Instead of waiting for the full audio file (2-3 seconds),
    # we send chunks as OpenAI generates them.  The frontend can
    # start playback after receiving the first chunk (~300-500ms).
    use_provider = tts_provider or voice_config.DEFAULT_TTS_PROVIDER
    use_voice = tts_voice or voice_config.TTS_VOICE
    tts_adapter = get_tts_adapter(use_provider)
    supports_streaming = hasattr(tts_adapter, "generate_speech_stream")

    # Tell the caller audible output is about to start (Flux barge-in).
    if on_audio_start is not None:
        try:
            on_audio_start()
        except Exception as exc:
            logger.error(f"[{session_id}] on_audio_start callback failed: {exc}")

    if supports_streaming and tutor_voice_text:
        # -- Streaming path (OpenAI) --
        if not _websocket_is_connected(ws):
            logger.info(f"[{session_id}] Client closed before audio streaming")
            return
        tts_start = time.time()
        chunk_index = 0

        try:
            async for chunk in tts_adapter.generate_speech_stream(
                text=tutor_voice_text,
                voice=use_voice,
                audio_format="mp3",
            ):
                if not _websocket_is_connected(ws):
                    logger.info(f"[{session_id}] Client closed during audio streaming")
                    return
                chunk_b64 = base64.b64encode(chunk).decode("utf-8")

                sent = await _send_json_if_connected(ws, {
                    "type": "tutor_audio_chunk",
                    "chunk": chunk_b64,
                    "chunk_index": chunk_index,
                })
                if not sent:
                    logger.info(f"[{session_id}] Client closed during audio streaming")
                    return

                if chunk_index == 0:
                    first_chunk_ms = int((time.time() - tts_start) * 1000)
                    logger.info(
                        f"[{session_id}] First audio chunk sent: {first_chunk_ms}ms"
                    )

                chunk_index += 1

            tts_latency = int((time.time() - tts_start) * 1000)

            # Step 3: Tell frontend that audio is done
            await _send_json_if_connected(ws, {
                "type": "tutor_audio_end",
                "total_chunks": chunk_index,
                "tts_latency_ms": tts_latency,
            })

            logger.info(
                f"[{session_id}] Audio streaming done: "
                f"{chunk_index} chunks in {tts_latency}ms"
            )

        except Exception as e:
            logger.error(f"[{session_id}] Streaming TTS failed: {e}")
            # Tell frontend audio won't be coming
            await _send_json_if_connected(ws, {
                "type": "tutor_audio_end",
                "total_chunks": 0,
                "tts_latency_ms": 0,
                "error": str(e),
            })

    elif tutor_voice_text:
        # -- Fallback: non-streaming path (mock, deepgram, etc.) --
        # Generate full audio and send it as a single chunk.
        try:
            tts_start = time.time()

            tts_result = await tts_adapter.generate_speech(
                text=tutor_voice_text,
                voice=use_voice,
                audio_format="mp3",
            )

            tts_latency = int((time.time() - tts_start) * 1000)

            audio_data = tts_result.audio_data
            if isinstance(audio_data, str):
                audio_data = audio_data.encode("utf-8")
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

            # Send as single chunk so frontend uses same handling
            audio_sent = await _send_json_if_connected(ws, {
                "type": "tutor_audio_chunk",
                "chunk": audio_b64,
                "chunk_index": 0,
            })
            if not audio_sent:
                logger.info(f"[{session_id}] Client closed before audio delivery")
                return

            await _send_json_if_connected(ws, {
                "type": "tutor_audio_end",
                "total_chunks": 1,
                "tts_latency_ms": tts_latency,
            })

            logger.info(f"[{session_id}] TTS (non-streaming): {tts_latency}ms")

        except Exception as e:
            logger.error(f"[{session_id}] TTS fallback failed: {e}")
            await _send_json_if_connected(ws, {
                "type": "tutor_audio_end",
                "total_chunks": 0,
                "tts_latency_ms": 0,
                "error": str(e),
            })

    else:
        # No voice text to synthesize
        await _send_json_if_connected(ws, {
            "type": "tutor_audio_end",
            "total_chunks": 0,
            "tts_latency_ms": 0,
        })

    total_ms = int((time.time() - pipeline_start) * 1000)
    logger.info(f"[{session_id}] Pipeline complete: {total_ms}ms total")

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("VOICE_PORT", "8004"))
    logger.info(f"Starting voice streaming server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
