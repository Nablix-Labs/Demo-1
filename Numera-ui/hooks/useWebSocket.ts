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
import { ANON_ACCESS_TOKEN, studentId, voiceTurnFailedMessage, type QuestionType } from '@/lib/api';
import { resetSessionStart } from '@/hooks/useDemoTutor';
import { applyInteractionSupport, acceptResponse, type SupportPresentation } from '@/lib/interactionPresentation';
import { TurnWatchdog } from '@/lib/turnWatchdog';
import { SpeechSettleTimer } from '@/lib/speechSettle';
import { turnContextFrame } from '@/lib/voiceTurnContext';
import { reportFailure } from '@/lib/failureReport';


/**
 * Print every voice frame, in and out, with its full JSON.
 *
 * The REST path has always logged its payloads ("→ POST /interaction" and the
 * reply), so a tester debugging a typed turn can read exactly what crossed the
 * wire. The socket logged almost nothing — status lines, errors, unknown types
 * — and on the server transport a voice turn IS the socket. DevTools does not
 * fill the gap either: WebSocket frames are not network entries, they are
 * buried in the Messages tab of the one /voice/stream connection, so nothing
 * about a voice turn showed up where anyone looks for it (asked directly,
 * 7 Aug).
 *
 * Audio frames are excluded on purpose. They arrive around fifty a second and
 * carry base64 payloads; logging them would bury the frames that matter and
 * make the console useless for exactly the person this is for.
 */
const AUDIO_FRAMES = new Set(['audio_chunk', 'tutor_audio_chunk']);

function logFrame(direction: 'in' | 'out', msg: Record<string, unknown>): void {
  const type = String(msg.type ?? 'unknown');
  if (AUDIO_FRAMES.has(type)) return;
  const arrow = direction === 'in' ? '←' : '→';
  const colour = direction === 'in' ? '#2f7d5b' : '#7a5cc8';
  console.log(`%c[voice ${arrow}] ${type}`, `color:${colour};font-weight:bold`, msg);
}

function logBoundary(event: string, fields: Record<string, unknown>): void {
  console.info(event, {
    timestamp: new Date().toISOString(),
    ...fields,
  });
}

/** Reconnect back-off: base 3s, doubling per consecutive failure, capped. */
const RETRY_BASE_MS = 3_000;
const RETRY_MAX_MS = 30_000;
/** After the watchdog's rescue `stop`, how long the server gets to answer it
 *  before the turn is declared failed to the student. */
const RESCUE_GRACE_MS = 8_000;

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const watchdogRef = useRef<TurnWatchdog | null>(null);
  const processingTimerRef = useRef<SpeechSettleTimer | null>(null);
  /** Pending reconnect timer. Held so cleanup can cancel it — an uncancelled
   *  one reopened sockets after unmount and, after a sessionId change, from a
   *  stale closure over the OLD session (two live sockets, doubled audio). */
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryAttemptRef = useRef(0);
  const rescueGraceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Id of the rescue's "Something went wrong" bubble, so a reply that lands
   *  after the rescue can retract the now-false apology. */
  const rescueMsgIdRef = useRef<string | null>(null);
  /** True while the frames arriving belong to a tutor_response that was
   *  REJECTED by the ordering gate. The server streams one reply at a time on
   *  the socket, so everything up to the next tutor_response is that stale
   *  reply's audio — playing it would splice an abandoned answer into the
   *  next one. */
  const discardAudioRef = useRef(false);
  // Individual action selectors — subscribing to the whole store re-rendered
  // the entire lesson tree on every partial transcript (several per second
  // while the student speaks; felt as hitching on low-end tablets).
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const updatePartialTranscript = useNumeraStore((s) => s.updatePartialTranscript);
  const commitPartialTranscript = useNumeraStore((s) => s.commitPartialTranscript);
  const setSessionState = useNumeraStore((s) => s.setSessionState);
  const setVoiceStatus = useNumeraStore((s) => s.setVoiceStatus);
  const applyCanvasDraw = useNumeraStore((s) => s.applyCanvasDraw);
  // Reconnect when the voice picker changes: the provider/voice ride in the
  // socket URL, so an open socket keeps the old voice until a reconnect. These
  // subscriptions put them in connect()'s dependency chain — the effect below
  // then closes the old socket and opens one with the new voice.
  const ttsProvider = useNumeraStore((s) => s.ttsProvider);
  const ttsVoice = useNumeraStore((s) => s.ttsVoice);

  /** Send a control message (start/stop) to the voice server. */
  const sendControl = useCallback((type: string, extra?: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const frame = { type, ...extra };
      logFrame('out', frame);
      wsRef.current.send(JSON.stringify(frame));
    } else {
      // Dropping silently made rescues invisible: the watchdog's `stop` and
      // every turn_context could vanish with no trace in the console.
      console.warn(`[WS] dropped '${type}' — socket not open`);
    }
  }, []);

  /**
   * Tell the server which turn the next utterance belongs to.
   *
   * Must go out at the start of EVERY student turn: the server clears its
   * latched turn fields once a turn is processed, so one frame per connection
   * would only ever fix the first turn. See lib/voiceTurnContext.ts.
   */
  const sendTurnContext = useCallback(() => {
    const s = useNumeraStore.getState();
    const frame = turnContextFrame(s.currentTurnId, s.lastTutorTurnId);
    if (!frame) return;
    const { type, ...fields } = frame;
    sendControl(type, fields);
  }, [sendControl]);

  const connect = useCallback(() => {
    if (!sessionId || !voiceStreamingEnabled) return;
    // One pending reconnect at a time; a connect supersedes any queued retry.
    if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }

    // Same resolver the REST path uses, so the streamed voice matches the one
    // the student heard in the diagnostic. Passing the raw store values here
    // sent nothing until the picker was opened, and the server then fell back
    // to its env default — a different voice mid-session.
    const ws = new WebSocket(buildVoiceStreamUrl(sessionId, studentId(), effectiveVoice()));
    wsRef.current = ws;
    discardAudioRef.current = false;

    // The student's words have stopped arriving, so the server has taken the
    // turn and the tutor is working on it. Say PROCESSING rather than leaving
    // the panel reading "Listening…" while nobody is listening — that is the
    // state a tester reads as the tutor ignoring them.
    processingTimerRef.current?.cancel();
    processingTimerRef.current = new SpeechSettleTimer(() => {
      const store = useNumeraStore.getState();
      // Only from LISTENING: if the tutor already started speaking, or a newer
      // turn opened, this settle belongs to a turn that is no longer current.
      if (store.voiceStatus !== 'listening') return;
      store.setVoiceStatus('processing');
    });

    watchdogRef.current?.dispose();
    watchdogRef.current = new TurnWatchdog((armedTurnId) => {
      // A stray final (echo, noise) can arm the watchdog with no turn behind
      // it; if the lesson has since moved on, firing `stop` now would land in
      // the middle of a DIFFERENT turn — and the server's stop handler cancels
      // work in flight. Only rescue the turn this was armed for.
      if (armedTurnId !== useNumeraStore.getState().currentTurnId) return;
      console.warn('[WS] no tutor reply for a transcribed turn — forcing finalisation');
      sendControl('stop');
      // The rescue used to end here: fire `stop`, log, done. If the stop
      // produced nothing (or the socket was already closed, where sendControl
      // silently no-ops) the panel sat at "Processing…" with the mic shut for
      // the rest of the session. Give the stop a grace window, then tell the
      // student and hand the floor back.
      if (rescueGraceRef.current) clearTimeout(rescueGraceRef.current);
      rescueGraceRef.current = setTimeout(() => {
        rescueGraceRef.current = null;
        const store = useNumeraStore.getState();
        if (store.currentTurnId !== armedTurnId) return; // something resolved it
        // Keep the apology's id: replies have been observed landing AFTER this
        // rescue (53s past utterance end, 10 Aug), and "Something went wrong"
        // sitting above "Nice work!" reads as a contradiction. If that happens,
        // the tutor_response handler retracts this bubble.
        rescueMsgIdRef.current = addTranscriptMessage({ role: 'ai', text: voiceTurnFailedMessage() });
        store.beginListeningTurn();
        sendTurnContext();
      }, RESCUE_GRACE_MS);
    });

    ws.onopen = () => {
      if (wsRef.current !== ws) { ws.close(1000, 'superseded'); return; }
      retryAttemptRef.current = 0;
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
      // A fresh socket is a fresh listening turn. Mint one if the lesson hasn't
      // already, so the very first utterance carries a turn_id like every
      // later one does.
      if (!useNumeraStore.getState().currentTurnId) {
        useNumeraStore.getState().beginListeningTurn();
      }
      setVoiceStatus('listening');
      sendTurnContext();
    };

    ws.onmessage = (event: MessageEvent) => {
      // An orphaned socket (superseded by a reconnect) must not handle frames —
      // two live handlers meant two tutor voices and duplicated transcripts.
      if (wsRef.current !== ws) return;
      try {
        const msg = JSON.parse(event.data as string) as Record<string, unknown>;
        logFrame('in', msg);

        switch (msg.type) {
          case 'transcript_partial':
            updatePartialTranscript(msg.text as string);
            // Still talking — anything pending belongs to an unfinished turn.
            processingTimerRef.current?.noteSpeech();
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
              const store = useNumeraStore.getState();
              logBoundary('VOICE_FINAL_TRANSCRIPT', {
                session_id: sessionId,
                interaction_id: store.currentTurnId,
                question_id: store.activeQuestionId,
                transcript: msg.text,
                confidence: msg.confidence,
                transcript_final: msg.is_final === true,
                processing_state: store.voiceStatus,
              });
            } else {
              addTranscriptMessage({ role: msg.role as 'ai' | 'student', text: msg.text as string });
            }
            // The student said something the server heard. From here a reply is
            // owed, and only Deepgram's UtteranceEnd will ask for one — so start
            // the rescue clock in case that event never arrives.
            // A final is per Deepgram SEGMENT, not per turn — "It is" can be
            // final while the student is still saying "…5". So this restarts
            // the settle clock like a partial does; it does not end the turn.
            if (msg.role === 'student') {
              watchdogRef.current?.noteStudentSpeech(useNumeraStore.getState().currentTurnId);
              processingTimerRef.current?.noteSpeech();
            }
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
            processingTimerRef.current?.cancel();
            if (rescueGraceRef.current) { clearTimeout(rescueGraceRef.current); rescueGraceRef.current = null; }
            // A new reply starts a new audio stream; whatever was being
            // discarded is over.
            discardAudioRef.current = false;
            // Ordering guard (handoff item: "prevent a late response from an
            // earlier failed turn from overwriting a newer turn"). The REST
            // path has gone through this gate since Phase 2; the socket never
            // did, so a slow reply to an abandoned turn could land on top of a
            // newer one. Same rule, same bookkeeping, both transports.
            if (!acceptResponse(msg as Parameters<typeof acceptResponse>[0])) {
              console.log('[WS] stale tutor_response dropped', {
                version: msg.interaction_state_version,
                accepted_turn_id: msg.accepted_turn_id,
              });
              // The dropped reply's AUDIO is still about to stream in. The
              // server sends one reply at a time on this socket, so every
              // audio frame until the next tutor_response is that stale
              // reply's — playing it would splice an abandoned answer into
              // whatever comes next.
              discardAudioRef.current = true;
              // Nothing is in flight any more; let the student speak again.
              useNumeraStore.getState().beginListeningTurn();
              sendTurnContext();
              break;
            }
            // A reply landing after the rescue makes the rescue's apology false
            // ("Something went wrong" directly above "Nice work!" — Manjusha,
            // 10 Aug). Retract it, but only while it is still the newest AI
            // bubble: once the conversation has moved past it, deleting a
            // message from mid-history is more confusing than the apology.
            if (rescueMsgIdRef.current) {
              const transcript = useNumeraStore.getState().transcript;
              const lastAi = [...transcript].reverse().find((m) => m.role === 'ai');
              if (lastAi?.id === rescueMsgIdRef.current) {
                useNumeraStore.getState().removeTranscriptMessage(lastAi.id);
              }
              rescueMsgIdRef.current = null;
            }
            addTranscriptMessage({ role: 'ai', text: msg.text as string });
            logBoundary('INTERACTION_RESPONSE', {
              session_id: sessionId,
              interaction_id: msg.accepted_turn_id,
              question_id: msg.question_id ?? useNumeraStore.getState().activeQuestionId,
              transcript: msg.transcript,
              status: 'tutor_response',
              processing_state: 'received',
            });
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
                // The voice server does not always forward this. Passing
                // undefined rather than null lets applyBackendPhase keep the
                // type it already has instead of blanking a choice question
                // into a free-response one mid-lesson.
                questionType:
                  typeof msg.question_type === 'string'
                    ? (msg.question_type as QuestionType)
                    : undefined,
              });
            }
            // Record the tutor turn, exactly as the REST path does (contract
            // §11, useDemoTutor). This was missing entirely, and setTutorTurn
            // had only ever been called there — so on the server transport
            // lastTutorTurnId stayed null for the whole session even though the
            // voice server forwards tutor_turn_id in this very frame.
            //
            // Everything keyed to the tutor turn was therefore dead here. The
            // visible one: inactivity nudges sent previous_tutor_turn_id: null,
            // which the backend rejects outright, so an idle student produced a
            // 422 on every tick instead of a nudge (7 Aug, VM).
            useNumeraStore.getState().setTutorTurn(
              (msg.tutor_turn_id as string | null) ?? null,
              {
                expects: (msg.expects_student_response as boolean | undefined) ?? true,
                allow: (msg.allow_voice_input as boolean | undefined) ?? true,
              },
            );
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
              // The REST path already honours this; the socket unconditionally
              // reopened the mic, so a reply that expects no answer (or forbids
              // voice) still had room noise transcribed and submitted as a turn.
              if (!store.expectsStudentResponse || !store.allowVoiceInput) {
                store.setVoiceStatus('waiting');
                return;
              }
              store.beginListeningTurn();
              // New turn, new id — and the server dropped the last one when it
              // finished this reply, so it needs the new one before the student
              // speaks again.
              sendTurnContext();
            });
            tutorAudioStream.begin(
              (typeof msg.voice_text === 'string' && msg.voice_text) || spokenLine,
            );
            break;

          case 'tutor_audio_chunk':
            if (discardAudioRef.current) break; // audio of a rejected stale reply
            tutorAudioStream.push(msg.chunk_index as number, msg.chunk as string);
            break;

          case 'tutor_audio_end':
            if (discardAudioRef.current) { discardAudioRef.current = false; break; }
            tutorAudioStream.finishStream(msg.total_chunks as number, msg.error as string | undefined);
            break;

          // Voice server status/error — informational, no UI action needed.
          case 'status':
            console.log('[WS] status:', msg.message);
            break;
          case 'error':
            // The server already gave up on this turn ("Tutor unavailable").
            // Nothing is stuck, so there is nothing to rescue — but the student
            // still has to be TOLD.
            //
            // This branch used to stand the watchdog down and log to the
            // console, and that was the whole handler. The turn then ended in
            // silence with the status still reading "Listening…", so a student
            // who had just answered sat waiting for a reply that was never
            // coming (reported 6 Aug: "she doesn't get proper response").
            //
            // The REST path has always mapped its failures through
            // studentFacingError, which is why this kept being reported as
            // voice-specific when it is not: the same backend failure is simply
            // announced on chat and swallowed here.
            watchdogRef.current?.noteTurnResolved();
            processingTimerRef.current?.cancel();
            const errorStore = useNumeraStore.getState();
            logBoundary('INTERACTION_ERROR', {
              session_id: sessionId,
              interaction_id: errorStore.currentTurnId,
              question_id: errorStore.activeQuestionId,
              transcript: errorStore.transcript.at(-1)?.text,
              status: 'voice_socket_error',
              error: msg.message,
              processing_state: errorStore.voiceStatus,
            });
            // Engineer-facing detail stays in the console — it is the backend's
            // own reason and the fastest way to find which service failed. The
            // full report matches what the REST path writes, because until now
            // this transport logged one line and the same backend fault kept
            // being filed as "voice is broken" rather than as itself.
            reportFailure(
              'voice socket',
              { config: { method: 'WS', url: '/voice/stream' }, message: msg.message },
              {
                session_id: useNumeraStore.getState().sessionId,
                question_id: useNumeraStore.getState().activeQuestionId,
                phase: useNumeraStore.getState().currentPhase,
                frame: msg,
              },
            );
            // A session the backend has forgotten (restart — its sessions are
            // in-memory) fails EVERY turn from here on; the REST path recovers
            // by dropping the dead session and starting fresh, but the socket
            // path had no equivalent, so only clearing localStorage got a
            // student out. Same recovery, this transport.
            if (/session.*(not.?found|was not found|unknown|expired)/i.test(String(msg.message ?? ''))) {
              console.warn('[WS] server no longer knows this session — starting a fresh one');
              resetSessionStart();
              useNumeraStore.getState().clearSessionId();
              break; // the lesson's start effect reopens a session; this socket closes with it
            }
            addTranscriptMessage({
              role: 'ai',
              text: voiceTurnFailedMessage(msg.message as string | undefined),
            });
            // Same as the REST path: the tutor owes them a reply, so the idle
            // clock must not read the silence that follows as being stuck and
            // ask what they would try first. This transport had the same hole.
            useNumeraStore.getState().markTutorTurnFailed();
            // The copy tells the student to say it again, so put them back in a
            // state where they can. Without this the panel could sit in
            // PROCESSING for a turn that already failed, with the mic shut.
            useNumeraStore.getState().beginListeningTurn();
            sendTurnContext();
            break;

          default:
            console.warn('[WS] unknown message type:', msg.type);
        }
      } catch (err) {
        console.error('[WS] parse error', err);
      }
    };

    // Without this the browser reports errors only via onclose; log the event
    // itself so a failed connect is distinguishable from a dropped one.
    ws.onerror = () => {
      if (wsRef.current !== ws) return;
      console.error('[WS] socket error (see close event for the code)');
    };

    ws.onclose = (e) => {
      if (wsRef.current !== ws) return; // an old socket dying is not news
      console.log('[WS] closed', e.code, e.reason);
      // A turn was in flight — the student spoke and the reply can no longer
      // arrive on this socket. It used to vanish without a word; tell them.
      const midTurn = watchdogRef.current?.armed ?? false;
      // A `stop` sent down a dead socket goes nowhere; the reconnect below
      // starts a fresh turn anyway.
      watchdogRef.current?.dispose();
      // Nothing is settling on a closed socket; a late fire would announce
      // PROCESSING for a turn that can no longer be processed.
      processingTimerRef.current?.cancel();
      if (rescueGraceRef.current) { clearTimeout(rescueGraceRef.current); rescueGraceRef.current = null; }
      setVoiceStatus('idle');
      if (midTurn) {
        addTranscriptMessage({
          role: 'ai',
          text: 'I lost the connection for a second there — say that again and I’ll pick it up.',
        });
      }
      // An auth close cannot be fixed by retrying — reconnecting every 3s
      // forever with the mic pinned shut and no message was the old behaviour.
      if (e.code === 4401 || e.code === 4403) {
        addTranscriptMessage({
          role: 'ai',
          text: 'Voice needs you to be signed in — log in again and I’ll be right here.',
        });
        return;
      }
      if (e.code !== 1000) {
        const delay = Math.min(RETRY_BASE_MS * 2 ** retryAttemptRef.current, RETRY_MAX_MS);
        retryAttemptRef.current += 1;
        retryRef.current = setTimeout(connect, delay);
      }
    };

  }, [sessionId, ttsProvider, ttsVoice, sendControl, sendTurnContext, addTranscriptMessage, updatePartialTranscript, commitPartialTranscript, setSessionState, setVoiceStatus, applyCanvasDraw]);

  useEffect(() => {
    connect();
    return () => {
      // The pending reconnect must die with the screen — it used to survive
      // unmount and open a socket onto whatever page came next.
      if (retryRef.current) { clearTimeout(retryRef.current); retryRef.current = null; }
      retryAttemptRef.current = 0;
      if (rescueGraceRef.current) { clearTimeout(rescueGraceRef.current); rescueGraceRef.current = null; }
      watchdogRef.current?.dispose();
      watchdogRef.current = null;
      processingTimerRef.current?.cancel();
      processingTimerRef.current = null;
      // The idle handler reopens the student's turn. tutorAudioStream is a
      // module singleton, so a handler left registered here outlives this
      // screen and would reopen a listening turn on whatever the student
      // navigated to — including a phase that expects no voice input at all.
      tutorAudioStream.setOnIdle(null);
      const ws = wsRef.current;
      wsRef.current = null; // orphan it first so its handlers no-op
      ws?.close(1000, 'component unmount');
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
      const frame = { type: 'text_message', text };
      logFrame('out', frame);
      wsRef.current.send(JSON.stringify(frame));
    }
  }, []);

  /** Send canvas PNG snapshot (+ optional stroke data) on "Check My Work" */
  const sendCanvasSubmission = useCallback((png: string, strokes?: object[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      logFrame('out', { type: 'canvas_submission', png_bytes: png.length, strokes });
      wsRef.current.send(JSON.stringify({ type: 'canvas_submission', png, strokes }));
    }
  }, []);

  return { sendAudioChunk, sendTextMessage, sendCanvasSubmission, sendControl };
}
