import os
import sys
import json
import time
import asyncio
import ssl
import certifi
import logging
import base64
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import websockets

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "adapters"))

import config as voice_config

from adapter import get_tts_adapter

import mock_adapter

if voice_config.OPENAI_API_KEY:
    import openai_tts_adapter

if voice_config.DEEPGRAM_API_KEY:
    import deepgram_tts_adapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("streaming")

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_API_KEY = voice_config.DEEPGRAM_API_KEY
MAIN_BACKEND_URL = os.getenv("NABLIX_MAIN_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

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
) -> dict[str, object]:
    payload = {
        "session_id": session_id,
        "student_id": student_id,
        "transcript": transcript,
        "confidence": confidence,
        "audio_duration_seconds": audio_duration_seconds,
        "turn": "STUDENT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(f"[{session_id}] POST /voice/transcript")
    response = await get_backend_http_client().post(
        "/voice/transcript",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
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


def _tutor_response_from_canvas(result: dict[str, object]) -> dict[str, object]:
    tutor = result.get("tutor")
    if not isinstance(tutor, dict):
        raise RuntimeError("canvas response missing tutor object")

    tutor_message = tutor.get("tutor_message")
    if not isinstance(tutor_message, str) or tutor_message == "":
        raise RuntimeError("canvas tutor response missing tutor_message")

    tutor_message_voice = tutor.get("tutor_message_voice")
    return {
        **_phase_fields_from(result),
        "message": tutor_message,
        "message_voice": tutor_message_voice if isinstance(tutor_message_voice, str) else tutor_message,
    }


PHASE_FIELDS = (
    "phase_changed",
    "previous_phase",
    "current_phase",
    "current_question",
    "question_id",
    "ui_state",
    "recommended_entry_phase",
    "phase_transition_message",
    "phase_transition_voice",
)


def _phase_fields_from(result: dict[str, object]) -> dict[str, object]:
    """Pass the backend's phase state through to the frontend unchanged."""
    return {key: result.get(key) for key in PHASE_FIELDS if key in result}


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


async def synthesize_speech(text: str) -> str | None:
    """Configured TTS (OpenAI when keyed) → base64 mp3; None on empty text.

    Retries provider failures per the adapter retry setting, then raises so the
    caller can return an explicit error (frontend falls back to browser speech).
    """
    if not text:
        return None
    attempts = _tts_retry_count() + 1
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            tts_adapter = get_tts_adapter(voice_config.DEFAULT_TTS_PROVIDER)
            result = await tts_adapter.generate_speech(
                text=text,
                voice=voice_config.TTS_VOICE,
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
        await tts_adapter.generate_speech(text=".", voice=voice_config.TTS_VOICE, audio_format="mp3")
        logger.info("TTS connection pre-warmed successfully")
    except Exception as e:
        logger.warning(f"TTS pre-warm failed (non-fatal): {e}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "voice-streaming"}

@app.websocket("/voice/stream")
async def voice_stream(ws: WebSocket, session: str = "default", student_id: str = "ST001"):
    session_id = session  # frontend sends ?session=, not ?session_id=
    await ws.accept()
    logger.info(f"[{session_id}] WebSocket connected")

    language = "en"
    deepgram_ws = None
    final_transcript = ""
    final_confidence = 0.0
    final_segment_count = 0
    receiving_audio = False
    audio_started_at = 0.0
    turn_already_processed = False  # True when UtteranceEnd auto-triggered a response
    access_token: str | None = None

    deepgram_receiver_task = None

    async def forward_deepgram_results(dg_ws):
        nonlocal final_transcript, final_confidence, final_segment_count, audio_started_at, turn_already_processed

        try:
            async for msg in dg_ws:
                data = json.loads(msg)

                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alternatives = channel.get("alternatives", [])

                    if not alternatives:
                        continue

                    best = alternatives[0]
                    transcript = best.get("transcript", "").strip()
                    confidence = best.get("confidence", 0.0)
                    is_final = data.get("is_final", False)

                    if not transcript:
                        continue

                    if is_final:
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

                    await ws.send_json({
                        "type": "transcript_partial" if not is_final else "transcript_final",
                        "text": transcript,
                        "confidence": round(confidence, 4),
                        "is_final": is_final,
                        "role": "student",
                    })

                    logger.info(
                        f"[{session_id}] {'FINAL' if is_final else 'partial'}: "
                        f"'{transcript}' (conf={confidence:.4f})"
                    )

                elif data.get("type") == "UtteranceEnd":
                    # Deepgram detected 1.5s silence after speech.
                    # Auto-trigger tutor response without requiring mic mute.
                    if final_transcript:
                        logger.info(
                            f"[{session_id}] UtteranceEnd - auto-processing: "
                            f"'{final_transcript}'"
                        )
                        transcript_to_process = final_transcript
                        confidence_to_process = final_confidence
                        duration = max(time.time() - audio_started_at, 0.001)

                        # Reset for potential next utterance in same session
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
                            )
                        except Exception as e:
                            logger.error(f"[{session_id}] Auto-process failed: {e}")

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

                if msg_type == "authenticate":
                    candidate = data.get("access_token")
                    if not isinstance(candidate, str) or candidate == "":
                        await ws.close(code=4401, reason="Authentication required")
                        return
                    access_token = candidate
                    await ws.send_json({"type": "status", "message": "authenticated"})

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

                    params = (
                        f"?model=nova-3"
                        f"&language={language}"
                        f"&smart_format=true"
                        f"&punctuate=true"
                        f"&interim_results=true"
                        f"&utterance_end_ms=1500"
                        f"&encoding=linear16"
                        f"&sample_rate=16000"
                        f"&channels=1"
                    )

                    dg_url = DEEPGRAM_WS_URL + params
                    extra_headers = {
                        "Authorization": f"Token {DEEPGRAM_API_KEY}"
                    }

                    logger.info(f"[{session_id}] Connecting to Deepgram streaming...")

                    ssl_context = ssl.create_default_context(cafile=certifi.where())

                    deepgram_ws = await websockets.connect(
                        dg_url,
                        additional_headers=extra_headers,
                        ssl=ssl_context,
                    )

                    logger.info(f"[{session_id}] Deepgram connected. Streaming started.")

                    deepgram_receiver_task = asyncio.create_task(
                        forward_deepgram_results(deepgram_ws)
                    )

                    await ws.send_json({
                        "type": "status",
                        "message": "streaming_started",
                    })

                elif msg_type == "stop":
                    receiving_audio = False
                    canvas_snapshot = data.get("canvas_snapshot")
                    logger.info(f"[{session_id}] Stop received. Finalizing...")

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
                        await process_and_respond(
                            ws, session_id, student_id, final_transcript,
                            final_confidence, audio_duration_seconds, access_token, canvas_snapshot
                        )
                    elif not turn_already_processed:
                        logger.info(f"[{session_id}] Stop: no speech detected")

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

                        params = (
                            f"?model=nova-3"
                            f"&language={language}"
                            f"&smart_format=true"
                            f"&punctuate=true"
                            f"&interim_results=true"
                            f"&utterance_end_ms=1500"
                            f"&encoding=linear16"
                            f"&sample_rate=16000"
                            f"&channels=1"
                        )
                        dg_url = DEEPGRAM_WS_URL + params
                        extra_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
                        ssl_context = ssl.create_default_context(cafile=certifi.where())

                        try:
                            deepgram_ws = await websockets.connect(
                                dg_url,
                                additional_headers=extra_headers,
                                ssl=ssl_context,
                            )
                            deepgram_receiver_task = asyncio.create_task(
                                forward_deepgram_results(deepgram_ws)
                            )
                            logger.info(f"[{session_id}] Deepgram auto-connected.")
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
        if deepgram_receiver_task and not deepgram_receiver_task.done():
            deepgram_receiver_task.cancel()
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
    canvas_snapshot: str | None = None,
):
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
            tutor_response = _tutor_response_from_canvas(canvas_response)
            canvas_draw = _canvas_draw_from(canvas_response)
        else:
            tutor_response = await evaluate_voice_transcript(
                session_id,
                student_id,
                transcript,
                confidence,
                audio_duration_seconds,
                access_token,
            )
        tutor_ms = int((time.time() - tutor_start) * 1000)
        logger.info(f"[{session_id}] Backend tutor call took {tutor_ms}ms")
    except Exception as e:
        logger.error(f"[{session_id}] Main backend tutor call failed: {e}")
        await ws.send_json({
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

    await ws.send_json({
        "type": "tutor_response",
        "transcript": transcript,
        "normalized_expression": normalized,
        "confidence": round(confidence, 4),
        "text": tutor_text,
        "voice_text": tutor_voice_text,
        "needs_clarification": confidence < voice_config.CONFIDENCE_THRESHOLD,
        "text_latency_ms": text_sent_ms,
        "canvas_draw": canvas_draw,
        **_phase_fields_from(tutor_response),
    })

    logger.info(f"[{session_id}] Text sent to frontend: {text_sent_ms}ms")

    # ---- Step 2: Stream TTS audio in chunks ----
    # Instead of waiting for the full audio file (2-3 seconds),
    # we send chunks as OpenAI generates them.  The frontend can
    # start playback after receiving the first chunk (~300-500ms).
    tts_adapter = get_tts_adapter(voice_config.DEFAULT_TTS_PROVIDER)
    supports_streaming = hasattr(tts_adapter, "generate_speech_stream")

    if supports_streaming and tutor_voice_text:
        # -- Streaming path (OpenAI) --
        tts_start = time.time()
        chunk_index = 0

        try:
            async for chunk in tts_adapter.generate_speech_stream(
                text=tutor_voice_text,
                voice=voice_config.TTS_VOICE,
                audio_format="mp3",
            ):
                chunk_b64 = base64.b64encode(chunk).decode("utf-8")

                await ws.send_json({
                    "type": "tutor_audio_chunk",
                    "chunk": chunk_b64,
                    "chunk_index": chunk_index,
                })

                if chunk_index == 0:
                    first_chunk_ms = int((time.time() - tts_start) * 1000)
                    logger.info(
                        f"[{session_id}] First audio chunk sent: {first_chunk_ms}ms"
                    )

                chunk_index += 1

            tts_latency = int((time.time() - tts_start) * 1000)

            # Step 3: Tell frontend that audio is done
            await ws.send_json({
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
            await ws.send_json({
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
                voice=voice_config.TTS_VOICE,
                audio_format="mp3",
            )

            tts_latency = int((time.time() - tts_start) * 1000)

            audio_data = tts_result.audio_data
            if isinstance(audio_data, str):
                audio_data = audio_data.encode("utf-8")
            audio_b64 = base64.b64encode(audio_data).decode("utf-8")

            # Send as single chunk so frontend uses same handling
            await ws.send_json({
                "type": "tutor_audio_chunk",
                "chunk": audio_b64,
                "chunk_index": 0,
            })

            await ws.send_json({
                "type": "tutor_audio_end",
                "total_chunks": 1,
                "tts_latency_ms": tts_latency,
            })

            logger.info(f"[{session_id}] TTS (non-streaming): {tts_latency}ms")

        except Exception as e:
            logger.error(f"[{session_id}] TTS fallback failed: {e}")
            await ws.send_json({
                "type": "tutor_audio_end",
                "total_chunks": 0,
                "tts_latency_ms": 0,
                "error": str(e),
            })

    else:
        # No voice text to synthesize
        await ws.send_json({
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
