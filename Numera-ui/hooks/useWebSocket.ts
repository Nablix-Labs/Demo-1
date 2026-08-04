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
import { useAuthStore } from '@/store/useAuthStore';
import { tutorAudioStream, effectiveVoice } from '@/lib/tts';
import { buildVoiceStreamUrl, voiceStreamingEnabled, allowAnonTutorCalls } from '@/lib/runtimeConfig';
import { ANON_ACCESS_TOKEN, studentId } from '@/lib/api';
import { applyInteractionSupport, type SupportPresentation } from '@/lib/interactionPresentation';
import { TurnWatchdog } from '@/lib/turnWatchdog';

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const watchdogRef = useRef<TurnWatchdog | null>(null);
  const {
    addTranscriptMessage,
    updatePartialTranscript,
    commitPartialTranscript,
    setSessionState,
    setVoiceStatus,
    applyCanvasDraw,
  } = useNumeraStore();

  /** Send a control message (start/stop) to the voice server. */
  const sendControl = useCallback((type: string, extra?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...extra }));
    }
  }, []);

  const connect = useCallback(() => {
    if (!sessionId || !voiceStreamingEnabled) return;

    // Same resolver the REST path uses, so the streamed voice matches the one
    // the student heard in the diagnostic. Passing the raw store values here
    // sent nothing until the picker was opened, and the server then fell back
    // to its env default — a different voice mid-session.
    const ws = new WebSocket(buildVoiceStreamUrl(sessionId, studentId(), effectiveVoice()));
    wsRef.current = ws;

    watchdogRef.current?.dispose();
    watchdogRef.current = new TurnWatchdog(() => {
      console.warn('[WS] no tutor reply for a transcribed turn — forcing finalisation');
      sendControl('stop');
    });

    ws.onopen = () => {
      // Mirror the REST interceptor: fall back to the placeholder bearer when
      // there's no real login and anon testing is enabled, so the socket isn't
      // self-closed on the VM where sign-up doesn't log in yet.
      const accessToken =
        useAuthStore.getState().accessToken ?? (allowAnonTutorCalls ? ANON_ACCESS_TOKEN : null);
      if (!accessToken) {
        ws.close(4401, 'Authentication required');
        return;
      }
      ws.send(JSON.stringify({ type: 'authenticate', access_token: accessToken }));
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
            // A student's final transcript REPLACES the partial bubble it has
            // been growing; it is not a second message. Appending it left both
            // on screen — the dotted partial and the blue final — and because
            // Deepgram revises as it goes, the two often disagreed: "How to put
            // this" sitting above "How to do this question?" (Manjusha, 4 Aug).
            //
            // The REST transport already committed in place; only the WS path
            // appended, so this only ever showed on the server transport.
            if (msg.role === 'student') {
              commitPartialTranscript(msg.text as string);
            } else {
              addTranscriptMessage({ role: msg.role as 'ai' | 'student', text: msg.text as string });
            }
            // The student said something the server heard. From here a reply is
            // owed, and only Deepgram's UtteranceEnd will ask for one — so start
            // the rescue clock in case that event never arrives.
            if (msg.role === 'student') watchdogRef.current?.noteStudentSpeech();
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
            // The turn resolved on its own. Stand the rescue down before doing
            // anything else, so a slow render can't let it fire late and cancel
            // the audio that is about to stream in.
            watchdogRef.current?.noteTurnResolved();
            addTranscriptMessage({ role: 'ai', text: msg.text as string });
            // applyInteractionSupport returns the line the tutor should SAY —
            // the scaffold step's voice line when a panel is open, else the
            // message. Kept as the stream's fallback text below.
            const spokenLine = applyInteractionSupport({
              message: msg.text as string,
              show_visual_cue: msg.show_visual_cue as boolean | undefined,
              visual_cue: msg.visual_cue as SupportPresentation['visual_cue'],
              show_scaffold_panel: msg.show_scaffold_panel as boolean | undefined,
              scaffold_id: msg.scaffold_id as string | null | undefined,
              current_scaffold_step_id:
                msg.current_scaffold_step_id as string | null | undefined,
              scaffold_step_number:
                msg.scaffold_step_number as number | null | undefined,
              scaffold_step_text: msg.scaffold_step_text as string | null | undefined,
              scaffold_step_voice: msg.scaffold_step_voice as string | null | undefined,
              total_scaffold_steps:
                msg.total_scaffold_steps as number | null | undefined,
            });
            if (Array.isArray(msg.canvas_draw) && msg.canvas_draw.length > 0)
              applyCanvasDraw(msg.canvas_draw as Parameters<typeof applyCanvasDraw>[0]);
            // The voice server forwards the backend's phase state; keep the
            // store in sync so usePhaseRouting can follow phase changes.
            //
            // Gated on the PHASE only: requiring current_question to be a string
            // dropped the whole update, so the phase change never reached the
            // store and the routing never followed it. What a null question then
            // means depends on whether the phase moved — applyBackendPhase owns
            // that rule, and both transports go through it.
            if (typeof msg.current_phase === 'string') {
              useNumeraStore.getState().applyBackendPhase({
                phase: msg.current_phase as string,
                questionId: (msg.question_id as string | null) ?? null,
                questionText:
                  typeof msg.current_question === 'string' ? msg.current_question : null,
              });
            }
            // Reset the player; chunks are coming next. The voice line rides
            // along so a failed stream (tutor_audio_end with error — Cartesia
            // quota, 31 Jul) speaks through the REST fallback chain instead of
            // leaving guided practice silent.
            // SPEAKING from the moment the reply lands, not from the moment its
            // audio starts. Those are seconds apart (synthesis + buffering), and
            // the mic gate keys off this — leaving it open through that window
            // let the mic catch the tutor's opening words and answer them.
            setVoiceStatus('speaking');
            tutorAudioStream.setOnIdle(() => {
              const store = useNumeraStore.getState();
              if (store.voiceStatus !== 'speaking') return; // superseded meanwhile
              store.beginListeningTurn();
            });
            tutorAudioStream.begin(
              (typeof msg.voice_text === 'string' && msg.voice_text) || spokenLine,
            );
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
            // The server already gave up on this turn ("Tutor unavailable").
            // Nothing is stuck, so there is nothing to rescue.
            watchdogRef.current?.noteTurnResolved();
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
      // A `stop` sent down a dead socket goes nowhere; the reconnect below
      // starts a fresh turn anyway.
      watchdogRef.current?.dispose();
      setVoiceStatus('idle');
      // Simple exponential back-off reconnect (omit in production; use a library)
      if (e.code !== 1000) {
        setTimeout(connect, 3000);
      }
    };

  }, [sessionId, sendControl, addTranscriptMessage, updatePartialTranscript, commitPartialTranscript, setSessionState, setVoiceStatus, applyCanvasDraw]);

  useEffect(() => {
    connect();
    return () => {
      watchdogRef.current?.dispose();
      watchdogRef.current = null;
      // The idle handler reopens the student's turn. tutorAudioStream is a
      // module singleton, so a handler left registered here outlives this
      // screen and would reopen a listening turn on whatever the student
      // navigated to — including a phase that expects no voice input at all.
      tutorAudioStream.setOnIdle(null);
      wsRef.current?.close(1000, 'component unmount');
    };
  }, [connect]);

  /** Send a raw base64 PCM audio chunk to the backend */
  const sendAudioChunk = useCallback((base64: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'audio_chunk', data: base64 }));
    }
  }, []);

  /** Send a typed text message */
  const sendTextMessage = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'text_message', text }));
    }
  }, []);

  /** Send canvas PNG snapshot (+ optional stroke data) on "Check My Work" */
  const sendCanvasSubmission = useCallback((png: string, strokes?: object[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'canvas_submission', png, strokes }));
    }
  }, []);

  return { sendAudioChunk, sendTextMessage, sendCanvasSubmission, sendControl };
}
