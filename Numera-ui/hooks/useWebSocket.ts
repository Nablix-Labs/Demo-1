/**
 * Numera — Voice WebSocket hook
 *
 * Connects to wss://{env}/voice for bidirectional audio streaming.
 * The backend drives all session state via messages on this socket.
 *
 * Message schema (in):
 *   { type: 'transcript_partial', text: string }
 *   { type: 'transcript_final',   text: string, role: 'ai' | 'student' }
 *   { type: 'session_state',      state: SessionState }
 *   { type: 'ui_instruction',     instruction: object }
 *   // Streamed voice-server reply (:8004) — text first, then MP3 audio in chunks:
 *   { type: 'tutor_response',     text: string, voice_text: string, ... }
 *   { type: 'tutor_audio_chunk',  chunk: string, chunk_index: number }   // base64 MP3
 *   { type: 'tutor_audio_end',    total_chunks: number, tts_latency_ms: number, error?: string }
 *
 * Message schema (out):
 *   { type: 'audio_chunk', data: string }  // base64 PCM 16kHz mono
 *   { type: 'text_message', text: string }
 *   { type: 'canvas_submission', png: string, strokes?: object[] }
 */
'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { tutorAudioStream } from '@/lib/tts';
import { buildVoiceStreamUrl, voiceStreamingEnabled } from '@/lib/runtimeConfig';

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const {
    addTranscriptMessage,
    updatePartialTranscript,
    setSessionState,
    setVoiceStatus,
    applyCanvasDraw,
  } = useNumeraStore();

  const connect = useCallback(() => {
    if (!sessionId || !voiceStreamingEnabled) return;

    const ws = new WebSocket(buildVoiceStreamUrl(sessionId));
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] connected');
      setVoiceStatus('listening');
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as Record<string, unknown>;

        switch (msg.type) {
          case 'transcript_partial':
            updatePartialTranscript(msg.text as string);
            break;

          case 'transcript_final':
            addTranscriptMessage({
              role: msg.role as 'ai' | 'student',
              text: msg.text as string,
            });
            break;

          case 'session_state':
            setSessionState(msg.state as Parameters<typeof setSessionState>[0]);
            break;

          case 'canvas_draw':
            // AI tutor draws on the canvas — normalised geometry, see CanvasDrawPayload
            applyCanvasDraw(msg as unknown as Parameters<typeof applyCanvasDraw>[0]);
            break;

          case 'ui_instruction':
            // Backend-controlled UI updates — extend this as the API matures
            console.log('[WS] ui_instruction', msg.instruction);
            break;

          // Voice-server reply (:8004): text arrives first, MP3 audio streams after.
          // Keep the socket OPEN — the audio chunks follow this message.
          case 'tutor_response':
            addTranscriptMessage({ role: 'ai', text: msg.text as string });
            if (Array.isArray(msg.canvas_draw) && msg.canvas_draw.length > 0)
              applyCanvasDraw(msg.canvas_draw as Parameters<typeof applyCanvasDraw>[0]);
            tutorAudioStream.begin(); // reset the player; chunks are coming next
            break;

          case 'tutor_audio_chunk':
            tutorAudioStream.push(msg.chunk_index as number, msg.chunk as string);
            break;

          case 'tutor_audio_end':
            tutorAudioStream.finishStream(msg.total_chunks as number, msg.error as string | undefined);
            break;

          // Voice server status/error — informational, no UI action needed.
          case 'status':
            console.log('[WS] status:', msg.message);
            break;
          case 'error':
            console.error('[WS] server error:', msg.message);
            break;

          default:
            console.warn('[WS] unknown message type:', msg.type);
        }
      } catch (err) {
        console.error('[WS] parse error', err);
      }
    };

    ws.onclose = (e) => {
      console.log('[WS] closed', e.code, e.reason);
      setVoiceStatus('idle');
      // Simple exponential back-off reconnect (omit in production; use a library)
      if (e.code !== 1000) {
        setTimeout(connect, 3000);
      }
    };

  }, [sessionId, addTranscriptMessage, updatePartialTranscript, setSessionState, setVoiceStatus, applyCanvasDraw]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close(1000, 'component unmount');
    };
  }, [connect]);

  /** Send a raw base64 PCM audio chunk to the backend */
  const sendAudioChunk = useCallback((base64: string) => {
    wsRef.current?.send(JSON.stringify({ type: 'audio_chunk', data: base64 }));
  }, []);

  /** Send a typed text message */
  const sendTextMessage = useCallback((text: string) => {
    wsRef.current?.send(JSON.stringify({ type: 'text_message', text }));
  }, []);

  /** Send canvas PNG snapshot (+ optional stroke data) on "Check My Work" */
  const sendCanvasSubmission = useCallback(
    (png: string, strokes?: object[]) => {
      wsRef.current?.send(
        JSON.stringify({ type: 'canvas_submission', png, strokes })
      );
    },
    []
  );

  /** Send a control message (start/stop) to the voice server. */
  const sendControl = useCallback((type: string, extra?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...extra }));
    }
  }, []);

  return { sendAudioChunk, sendTextMessage, sendCanvasSubmission, sendControl };
}
