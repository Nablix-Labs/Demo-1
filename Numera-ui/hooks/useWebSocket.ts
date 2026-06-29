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
 *
 * Message schema (out):
 *   { type: 'audio_chunk', data: string }  // base64 PCM 16kHz mono
 *   { type: 'text_message', text: string }
 *   { type: 'canvas_submission', png: string, strokes?: object[] }
 */
'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? '';

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
    if (!sessionId || !WS_URL) return;

    const ws = new WebSocket(`${WS_URL}?session=${sessionId}`);
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

    ws.onerror = (err) => {
      console.error('[WS] error', err);
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

  return { sendAudioChunk, sendTextMessage, sendCanvasSubmission };
}
