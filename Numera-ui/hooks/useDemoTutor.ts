'use client';

/**
 * useDemoTutor — the integration layer between the REST client (lib/api.ts) and
 * the UI store. It drives the demo happy path against the live backend:
 *
 *   start → submit canvas (live OCR) → tutor reply → hint → end
 *
 * Every step is recorded into the in-memory interaction trail so the History
 * view can show the full session, even though the backend stores no transcript.
 *
 * Backend calls are gated on NEXT_PUBLIC_API_BASE_URL: when it's unset (local
 * UI-only runs) the hook is a no-op so the mock UX keeps working untouched.
 */
import { useCallback } from 'react';
import {
  startSession,
  submitCanvas,
  sendInteraction,
  requestHint,
  endSession,
  toSessionSummary,
  STUDENT_ID,
  type SessionRecord,
  type SessionSummary,
  type CanvasSubmissionResult,
  type InteractionResponse,
  type HintResponse,
} from '@/lib/api';
import { useNumeraStore } from '@/store/useNumeraStore';
import { speakTutor } from '@/lib/tts';

const apiEnabled = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

// Monotonic voice-turn id. Each fired turn supersedes the previous one, so a slow
// or barged-over earlier turn can't append its reply after a newer turn has
// started — the cause of "which text is this reply answering?" in long chats.
let voiceTurnSeq = 0;

/**
 * True only when the student has actually drawn something. Guards against
 * sending blank canvas snapshots to the backend (and the live OCR provider) when
 * there's no activity. Read at call time so it doesn't re-subscribe the hook.
 */
function hasCanvasActivity(): boolean {
  return useNumeraStore.getState().items.length > 0;
}

/** Apply the backend's visual-cue instruction from an interaction response.
 *  Prefers the richer `visual_cue.show`, falling back to the flat
 *  `show_visual_cue`. No-ops when neither is present so a response that omits the
 *  field never hides an already-shown cue. */
function applyVisualCue(res: InteractionResponse): void {
  const cue = res.visual_cue;
  const show = cue?.show ?? res.show_visual_cue;
  if (typeof show === 'boolean') {
    useNumeraStore.getState().setVisualCue({
      show,
      cueType: cue?.cue_type ?? null,
      description: cue?.description ?? null,
    });
  }
}

/** Pull a human-readable message out of a normalised API error, if present. */
function errorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: { message?: string } } }).response?.data;
    if (data?.message) return data.message;
  }
  return err instanceof Error ? err.message : fallback;
}

// Shown in the chat when a tutor call fails (e.g. backend 5xx), so a failure is
// visible to the student instead of the chat silently freezing.
const TUTOR_UNAVAILABLE = "Sorry — I couldn't reach the tutor just now. Please try again in a moment.";
const HINT_UNAVAILABLE = "Sorry — I couldn't fetch a hint right now. Please try again in a moment.";

function syncBackendSession(response: {
  current_phase: string;
  current_question: string;
  question_id: string | null;
}): void {
  useNumeraStore.setState((state) => ({
    currentPhase: response.current_phase,
    activeQuestionId: response.question_id ?? state.activeQuestionId,
    questionText: response.current_question.replace(/^solve for\s*x\s*:?\s*/i, '').trim(),
  }));
}

export function useDemoTutor() {
  const sessionId = useNumeraStore((s) => s.sessionId);
  const setSessionId = useNumeraStore((s) => s.setSessionId);
  const canvasExporter = useNumeraStore((s) => s.canvasExporter);
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const addTrailEntry = useNumeraStore((s) => s.addTrailEntry);
  const clearTrail = useNumeraStore((s) => s.clearTrail);

  /** Begin a tutoring session for a concept. Returns the record, or null. */
  const start = useCallback(
    async (
      conceptId: string,
      mode: 'VOICE' | 'TEXT' = 'TEXT'
    ): Promise<SessionRecord | null> => {
      if (!apiEnabled()) return null;
      try {
        const rec = await startSession({
          student_id: STUDENT_ID,
          concept_id: conceptId,
          interaction_mode: mode,
        });
        clearTrail();
        setSessionId(rec.session_id);
        syncBackendSession(rec);
        addTrailEntry({ kind: 'question', text: rec.current_question });
        return rec;
      } catch (err) {
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not start session.') });
        return null;
      }
    },
    [setSessionId, addTrailEntry, clearTrail]
  );

  /** Send a typed student answer through the tutor pipeline. */
  const answer = useCallback(
    async (
      text: string,
      ctx: { concept_id: string; question_id: string; current_phase: string; hint_count: number }
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId) return null;
      addTrailEntry({ kind: 'answer', text });
      try {
        const state = useNumeraStore.getState();
        const res = await sendInteraction({
          session_id: sessionId,
          student_id: STUDENT_ID,
          interaction_type: 'ANSWER_SUBMISSION',
          input_source: 'TEXT',
          text_input: text,
          current_phase: state.currentPhase,
          concept_id: ctx.concept_id,
          question_id: state.activeQuestionId,
          hint_count: ctx.hint_count,
        });
        syncBackendSession(res);
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        if (res.current_phase) useNumeraStore.getState().setCurrentPhase(res.current_phase); // advance phase
        if (res.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw);
        applyVisualCue(res); // backend may ask to show/hide the supporting visual
        speakTutor(res.message); // voice the reply — same verbatim text shown in chat
        return res;
      } catch (err) {
        addTranscriptMessage({ role: 'ai', text: TUTOR_UNAVAILABLE }); // surface the failure in the chat
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Tutor unavailable.') });
        return null;
      }
    },
    [sessionId, addTranscriptMessage, addTrailEntry]
  );

  /** Export the current canvas and submit it for live OCR + tutor feedback. */
  const submitCanvasWork = useCallback(async (): Promise<CanvasSubmissionResult | null> => {
    if (!apiEnabled() || !sessionId) return null;
    const png = hasCanvasActivity() ? canvasExporter?.() : null;
    if (!png) {
      addTrailEntry({ kind: 'tutor', text: 'Nothing on the canvas to submit yet.' });
      return null;
    }
    try {
      const res = await submitCanvas(sessionId, png, 'STANDALONE_ATTEMPT');
      // Canvas responses now carry the same phase state as /interaction, so a
      // backend phase change here also drives usePhaseRouting.
      if (res.current_phase && res.current_question) {
        syncBackendSession({
          current_phase: res.current_phase,
          current_question: res.current_question,
          question_id: res.question_id ?? null,
        });
      }
      addTrailEntry({
        kind: 'canvas',
        text: res.ocr.raw_ocr_text || res.ocr.detected_equation || 'Canvas submitted.',
        meta: `OCR ${(res.ocr.confidence * 100).toFixed(0)}%${
          res.ocr.needs_clarification ? ' · needs clarification' : ''
        }`,
      });
      addTranscriptMessage({ role: 'ai', text: res.tutor.tutor_message });
      addTrailEntry({
        kind: 'tutor',
        text: res.tutor.tutor_message,
        meta: res.tutor.evaluation,
      });
      if (res.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw);
      speakTutor(res.tutor.tutor_message); // voice the reply — same verbatim text shown in chat
      return res;
    } catch (err) {
      addTranscriptMessage({ role: 'ai', text: TUTOR_UNAVAILABLE }); // surface the failure in the chat
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not read the canvas.') });
      return null;
    }
  }, [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]);

  /** Ask for the next hint. */
  const hint = useCallback(
    async (
      ctx: { concept_id: string; question_id: string; current_phase: string; current_hint_count: number }
    ): Promise<HintResponse | null> => {
      if (!apiEnabled() || !sessionId) return null;
      try {
        const state = useNumeraStore.getState();
        const res = await requestHint({
          session_id: sessionId,
          student_id: STUDENT_ID,
          current_phase: state.currentPhase,
          current_hint_count: ctx.current_hint_count,
          concept_id: ctx.concept_id,
          question_id: state.activeQuestionId,
        });
        addTranscriptMessage({ role: 'ai', text: res.hint });
        addTrailEntry({ kind: 'hint', text: res.hint, meta: `Hint ${res.hint_level}` });
        speakTutor(res.hint); // voice the hint — same verbatim text shown in chat
        return res;
      } catch (err) {
        addTranscriptMessage({ role: 'ai', text: HINT_UNAVAILABLE }); // surface the failure in the chat
        addTrailEntry({ kind: 'hint', text: errorMessage(err, 'No hint available.') });
        return null;
      }
    },
    [sessionId, addTranscriptMessage, addTrailEntry]
  );

  /**
   * Fire one completed voice turn to the backend: snapshot the canvas, then send
   * the transcript + canvas reference through /interaction, and speak the reply.
   * This is the function the turn-end detector calls when the student stops.
   */
  const submitVoiceTurn = useCallback(
    async (
      transcript: string,
      ctx: { concept_id: string; question_id: string; current_phase: string; hint_count: number },
      confidence?: number
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId || !transcript.trim()) return null;
      // Overlap guard (contract §5): never submit while another turn is processing.
      if (useNumeraStore.getState().voiceStatus === 'processing') {
        console.warn('[voice] turn ignored — a previous turn is still processing');
        return null;
      }
      const myTurn = ++voiceTurnSeq; // claim this turn; later turns supersede it
      // Enter PROCESSING: the mic closes (half-duplex), duplicate submits are blocked.
      useNumeraStore.getState().setVoiceStatus('processing');
      addTrailEntry({ kind: 'answer', text: transcript });
      // Show the student's complete spoken turn in the chat by finalizing the live
      // partial bubble in place (commitPartialTranscript) rather than appending a
      // fresh one — so the words don't jump from the live caption to a new bubble.
      // Falls back to appending when there's no partial (e.g. server transport).
      useNumeraStore.getState().commitPartialTranscript(transcript);

      // Console trace for backend integration debugging — shows the exact
      // payloads/responses the frontend exchanges on a voice turn.
      console.groupCollapsed(`%c[voice→backend] turn fired`, 'color:#7a5cc8;font-weight:bold');
      console.log('captured transcript:', transcript, confidence != null ? `(confidence ${confidence})` : '');

      // Snapshot the canvas alongside the spoken turn — only if the student
      // actually drew something (don't send blank canvases to the backend/OCR).
      let canvasSnapshotId: string | undefined;
      const png = hasCanvasActivity() ? canvasExporter?.() : null;
      if (png) {
        try {
          console.log('→ POST /canvas/submit', { session_id: sessionId, student_id: STUDENT_ID, snapshot_bytes: png.length });
          const canvasRes = await submitCanvas(sessionId, png, 'VOICE_ATTACHMENT');
          canvasSnapshotId = canvasRes.submission_id;
          console.log('← /canvas/submit', { submission_id: canvasRes.submission_id, ocr: canvasRes.ocr, tutor: canvasRes.tutor });
          if (canvasRes.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(canvasRes.canvas_draw);
          addTrailEntry({
            kind: 'canvas',
            text: canvasRes.ocr.raw_ocr_text || canvasRes.ocr.detected_equation || 'Canvas submitted.',
            meta: `OCR ${(canvasRes.ocr.confidence * 100).toFixed(0)}%`,
          });
        } catch (err) {
          console.warn('✗ /canvas/submit failed:', err);
          /* canvas is optional for a voice turn */
        }
      } else {
        console.log('(no canvas content this turn)');
      }

      try {
        const state = useNumeraStore.getState();
        const interactionReq = {
          session_id: sessionId,
          student_id: STUDENT_ID,
          interaction_type: 'ANSWER_SUBMISSION' as const,
          input_source: 'VOICE' as const,
          voice_transcript: transcript,
          transcript_confidence: confidence,
          canvas_snapshot_id: canvasSnapshotId,
          current_phase: state.currentPhase,
          concept_id: ctx.concept_id,
          question_id: state.activeQuestionId,
          hint_count: ctx.hint_count,
          // Voice turn-sync contract (§5): identify the turn so the backend can
          // dedupe/reject stale turns. transcript_final is always true here.
          turn_id: state.currentTurnId ?? undefined,
          previous_tutor_turn_id: state.lastTutorTurnId,
          transcript_final: true,
        };
        console.log('→ POST /interaction', interactionReq);
        const res = await sendInteraction(interactionReq);
        console.log('← /interaction', res);
        // A newer turn fired while we were waiting — drop this stale reply so it
        // can't append out of order under the wrong student turn.
        if (myTurn !== voiceTurnSeq) {
          console.log('(superseded by a newer turn — reply dropped)');
          console.groupEnd();
          return null;
        }
        // Duplicate/stale turns (contract §6): the backend didn't evaluate them, so
        // don't append a reply, speak, or score — just reopen listening.
        if (res.status === 'DUPLICATE_TURN' || res.status === 'STALE_TURN') {
          console.log(`(${res.status} — not applied)`);
          console.groupEnd();
          useNumeraStore.getState().beginListeningTurn();
          return null;
        }
        syncBackendSession(res);
        console.groupEnd();
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        if (res.current_phase) useNumeraStore.getState().setCurrentPhase(res.current_phase); // advance phase
        if (res.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw);
        applyVisualCue(res); // backend may ask to show/hide the supporting visual
        // Record the tutor turn + backend gating for the next turn (contract §11).
        // Fallbacks keep the loop working before the backend sends these fields.
        useNumeraStore.getState().setTutorTurn(res.tutor_turn_id ?? null, {
          expects: res.expects_student_response ?? true,
          allow: res.allow_voice_input ?? true,
        });
        // SPEAKING: mic stays closed while the tutor voices the reply (half-duplex,
        // contract §12). When audio ends, reopen a new LISTENING turn if the backend
        // expects another response; otherwise park in WAITING.
        useNumeraStore.getState().setVoiceStatus('speaking');
        const expectsMore = res.expects_student_response ?? true;
        // Speak exactly what's shown in the chat. The backend's message_voice can
        // carry the same meaning in different words ("we are close" vs "you're
        // almost there"), which is confusing when read + heard together — so the
        // spoken audio must match the on-screen text verbatim.
        speakTutor(res.message, () => {
          const store = useNumeraStore.getState();
          if (store.voiceStatus !== 'speaking') return; // superseded meanwhile
          if (expectsMore) store.beginListeningTurn();
          else store.setVoiceStatus('waiting');
        });
        return res;
      } catch (err) {
        console.warn('✗ /interaction failed:', err);
        console.groupEnd();
        addTranscriptMessage({ role: 'ai', text: TUTOR_UNAVAILABLE }); // surface the failure in the chat
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Tutor unavailable.') });
        useNumeraStore.getState().beginListeningTurn(); // reopen listening so the student can retry
        return null;
      }
    },
    [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]
  );

  /**
   * End the session and capture its summary + engine review for the Review
   * screen.
   *
   * On success: saves the summary and the engine review to the store and clears
   * sessionId (so the next topic starts a fresh session), and returns the
   * summary. Returns null when there's no live session to end (mock mode).
   * THROWS on request failure or when the response carries no usable summary or
   * review — the caller keeps the student on the current screen and shows an
   * error, and the backend leaves the session active.
   */
  const end = useCallback(async (): Promise<SessionSummary | null> => {
    if (!apiEnabled() || !sessionId) return null;
    const res = await endSession(sessionId); // propagates network/HTTP failures
    const summary = toSessionSummary(res);
    if (!summary) throw new Error('Session ended but no summary was returned.');
    if (!res.session_review) throw new Error('Session ended but no review was returned.');
    const store = useNumeraStore.getState();
    store.setSessionSummary(summary);
    store.setSessionReview(res.session_review);
    store.clearSessionId();
    return summary;
  }, [sessionId]);

  return {
    apiEnabled: apiEnabled(),
    sessionId,
    start,
    answer,
    submitCanvasWork,
    submitVoiceTurn,
    hint,
    end,
  };
}
