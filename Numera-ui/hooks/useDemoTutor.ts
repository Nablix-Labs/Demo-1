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
  endSession,
  toSessionSummary,
  studentId,
  questionProgress,
  type SessionRecord,
  type SessionSummary,
  type CanvasSubmissionResult,
  studentFacingError,
  type InteractionResponse,
} from '@/lib/api';
import { applyInteractionSupport, acceptResponse } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { tutorSay, setStudentWriting } from '@/lib/tutorSpeech';
import {
  availableSupport,
  nextSupport,
  LADDER_EXHAUSTED,
  type SupportRung,
} from '@/lib/supportLadder';

const apiEnabled = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

// Monotonic voice-turn id. Each fired turn supersedes the previous one, so a slow
// or barged-over earlier turn can't append its reply after a newer turn has
// started — the cause of "which text is this reply answering?" in long chats.
let voiceTurnSeq = 0;

/**
 * Session-start de-duplication. Module scope on purpose — a component ref does
 * NOT survive a remount, and AuthGate swaps `children` for a spinner whenever
 * the auth store changes, so any screen that opens a session can be torn down
 * and rebuilt at will.
 *
 * Without this, a screen that starts a session on mount and remounts in a loop
 * fires /session/start continuously. That is not theoretical: it exhausted the
 * backend's in-memory SESSION001–SESSION999 range on 2026-07-28, which 500s
 * every subsequent request until the service is restarted.
 *
 * `inFlight` collapses concurrent callers onto one request. `failedConcept`
 * stops an automatic retry after a failure — only an explicit retry (which
 * calls resetSessionStart) tries again.
 */
let inFlight: Promise<SessionRecord | null> | null = null;
let failedConcept: string | null = null;

/**
 * Student-facing reason the last session start failed, when the backend named
 * one. Without this a screen can only say "couldn't reach the tutor", which is
 * wrong and unactionable for the common case: the request landed and was
 * refused because the student id we sent isn't theirs (403 STUDENT_FORBIDDEN).
 */
let lastStartError: string | null = null;
export const sessionStartError = (): string | null => lastStartError;

/** Let an explicit user-driven retry attempt a failed concept again. */
export function resetSessionStart(): void {
  failedConcept = null;
  lastStartError = null;
}

/**
 * True only when the student has actually drawn something. Guards against
 * sending blank canvas snapshots to the backend (and the live OCR provider) when
 * there's no activity. Read at call time so it doesn't re-subscribe the hook.
 */
function hasCanvasActivity(): boolean {
  return useNumeraStore.getState().items.length > 0;
}

/** Pull a human-readable message out of a normalised API error, if present. */
/**
 * The developer-facing line that goes into the session trail.
 *
 * Prefixed with the HTTP status and error code when the request actually
 * reached a server. A trail entry reading "Tutor unavailable." is the same
 * sentence whether the socket never opened or the backend returned a 500 with a
 * detailed reason — and the two need completely different people to look at
 * them. This makes a screenshot of the trail enough to tell them apart.
 */
function errorMessage(err: unknown, fallback: string): string {
  const res = (err as { response?: { status?: number; data?: { message?: string; error_code?: string } } })?.response;
  if (res) {
    const parts = [`HTTP ${res.status ?? '?'}`];
    if (res.data?.error_code) parts.push(res.data.error_code);
    const detail = res.data?.message?.trim();
    return `${parts.join(' ')}${detail ? ` — ${detail}` : ''}`;
  }
  // No response object: the request genuinely never completed.
  return err instanceof Error ? `No response — ${err.message}` : fallback;
}

// Shown in the chat when a tutor call fails (e.g. backend 5xx), so a failure is
// visible to the student instead of the chat silently freezing.
const TUTOR_UNAVAILABLE = "Sorry — I couldn't reach the tutor just now. Please try again in a moment.";

/**
 * What the student sees in the chat when a tutor call fails.
 *
 * Some failures aren't "couldn't reach the tutor" at all — an auth rejection is a
 * request that landed and was refused, and telling the student to retry is wrong
 * advice they'll follow forever. Use specific copy when the backend named the
 * cause, otherwise the generic fallback. The developer-facing detail still goes
 * to the session trail and the console.
 */
function chatError(err: unknown, fallback: string): string {
  return studentFacingError(err) ?? fallback;
}

/**
 * Adopt the phase/question the backend just reported.
 *
 * A null question is a real state, not a missing value: orientation has no
 * question of its own, so the backend answers `question_id: null` there. This
 * used to fall back to the previous id (`?? state.activeQuestionId`), which kept
 * the diagnostic question on screen for the whole orientation and attached the
 * next turn to a question the student had already finished. Take the null.
 */
function syncBackendSession(response: {
  current_phase: string;
  current_question: string | null;
  question_id: string | null;
}): void {
  // Text is kept verbatim. This used to strip a leading "solve for x:" because
  // the screens re-added it themselves — which silently mangled any question
  // that wasn't a bare equation. The screens now decide presentation from the
  // text itself (lib/questionText.ts), so the backend's wording must survive.
  //
  // Whether a null question clears the current one depends on the phase; see
  // applyBackendPhase, which both transports share.
  const store = useNumeraStore.getState();
  store.applyBackendPhase({
    phase: response.current_phase,
    questionId: response.question_id,
    questionText: response.current_question,
  });

  // Progress rail (§2). The denominator only exists on the session record's
  // question set, so this is the one place both halves are known at once.
  const { index, total } = questionProgress(store.backendSession, response.question_id);
  store.setQuestionProgress(index, total);
}

/**
 * Open a tutoring session for a concept, at most once.
 *
 * Deliberately a plain module function, not part of the hook: the de-duplication
 * above only works if every caller shares it, and React identity (refs, callback
 * closures) resets on remount. Reads its store handles via getState() so it has
 * no React dependency at all — which is also what makes it testable.
 */
export async function beginSession(
  conceptId: string,
  mode: 'VOICE' | 'TEXT' = 'TEXT',
): Promise<SessionRecord | null> {
  if (!apiEnabled()) return null;
  const store = useNumeraStore.getState();
  // Already open — never mint a second session for the same run.
  if (store.sessionId) return store.backendSession;
  if (inFlight) return inFlight;
  if (failedConcept === conceptId) return null;

  inFlight = (async () => {
    try {
      const rec = await startSession({
        student_id: studentId(),
        concept_id: conceptId,
        interaction_mode: mode,
      });
      const s = useNumeraStore.getState();
      s.clearTrail();
      s.setSessionId(rec.session_id);
      s.setBackendSession(rec);
      syncBackendSession(rec);
      if (rec.current_question) s.addTrailEntry({ kind: 'question', text: rec.current_question });
      return rec;
    } catch (err) {
      // Latch the failure so a remount loop can't hammer the endpoint.
      failedConcept = conceptId;
      lastStartError = studentFacingError(err);
      useNumeraStore.getState().addTrailEntry({
        kind: 'tutor',
        text: errorMessage(err, 'Could not start session.'),
      });
      return null;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

export function useDemoTutor() {
  const sessionId = useNumeraStore((s) => s.sessionId);
  const canvasExporter = useNumeraStore((s) => s.canvasExporter);
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const addTrailEntry = useNumeraStore((s) => s.addTrailEntry);

  /** Begin a tutoring session for a concept. Returns the record, or null. */
  const start = useCallback(beginSession, []);

  /** Send a typed student answer through the tutor pipeline. */
  const answer = useCallback(
    async (
      text: string,
      ctx: { concept_id: string; current_phase: string; hint_count: number }
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId) return null;
      const questionId = useNumeraStore.getState().activeQuestionId;
      // No active question means the phase has none to answer (orientation).
      // /interaction requires a question_id, so sending here would 422.
      if (!questionId) return null;
      addTrailEntry({ kind: 'answer', text });
      const turnId = useNumeraStore.getState().beginSubmissionTurn();
      try {
        const state = useNumeraStore.getState();
        const res = await sendInteraction({
          session_id: sessionId,
          student_id: studentId(),
          interaction_type: 'ANSWER_SUBMISSION',
          input_source: 'TEXT',
          text_input: text,
          current_phase: state.currentPhase,
          concept_id: ctx.concept_id,
          question_id: questionId,
          hint_count: ctx.hint_count,
          // Typed answers used to carry no turn id at all, so the backend had
          // nothing to dedupe on and a retry was indistinguishable from a second
          // answer. Minted once here and reused verbatim on a retry.
          turn_id: turnId,
          previous_tutor_turn_id: state.lastTutorTurnId,
        });
        // Ordering guard (handoff item 2): a response older than what is on
        // screen is dropped, and a cached replay is applied exactly once.
        if (!acceptResponse(res)) return res;
        syncBackendSession(res);
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        if (res.current_phase) useNumeraStore.getState().setCurrentPhase(res.current_phase); // advance phase
        const drew = Boolean(res.canvas_draw?.length);
        if (drew) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw!);
        const spoken = applyInteractionSupport(res);
        // §1: highlight first, pause, then speak. When the turn also drew, the
        // mark lands before it is described; when it didn't, this speaks at once.
        tutorSay(spoken, { afterMarks: drew });
        return res;
      } catch (err) {
        addTranscriptMessage({ role: 'ai', text: chatError(err, TUTOR_UNAVAILABLE) }); // surface the failure in the chat
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
      const drew = Boolean(res.canvas_draw?.length);
      if (drew) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw!);
      // The work has been read, so the student no longer holds the floor —
      // otherwise the tutor's response to a submission would be silently dropped
      // by the very rule that kept it quiet while they were writing.
      setStudentWriting(false);
      tutorSay(res.tutor.tutor_message, { afterMarks: drew });
      return res;
    } catch (err) {
      addTranscriptMessage({ role: 'ai', text: chatError(err, TUTOR_UNAVAILABLE) }); // surface the failure in the chat
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not read the canvas.') });
      return null;
    }
  }, [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]);

  /**
   * Explain Again — replay the current explanation.
   *
   * Neither an answer nor a help escalation (Phase 2 handoff, Manav — Frontend,
   * Explain Again 2). The frontend computes nothing: no attempts, no components,
   * no support progression, no scaffold changes. It sends the request and
   * renders exactly what comes back.
   *
   * `EXPLAIN_AGAIN` does not exist on the backend yet, so a 4xx falls back to
   * re-showing the cue we already hold. That fallback is safe for the same
   * reason the control is: replaying what the tutor already said cannot be
   * graded, so it cannot cost the student an attempt either way.
   */
  const explainAgain = useCallback(async (): Promise<InteractionResponse | null> => {
    const s = useNumeraStore.getState();
    const replayLocally = () => {
      s.setVisualCueVisible(true);
      if (s.visualCueDescription) tutorSay(s.visualCueDescription, { afterMarks: true });
    };

    if (!apiEnabled() || !sessionId || !s.activeQuestionId) {
      replayLocally();
      return null;
    }

    const turnId = useNumeraStore.getState().beginSubmissionTurn();
    try {
      const res = await sendInteraction({
        session_id: sessionId,
        student_id: studentId(),
        interaction_type: 'EXPLAIN_AGAIN',
        input_source: 'TEXT',
        current_phase: s.currentPhase,
        concept_id: s.activeConceptId,
        question_id: s.activeQuestionId,
        hint_count: s.lastHintText ? 1 : 0,
        turn_id: turnId,
        previous_tutor_turn_id: s.lastTutorTurnId ?? null,
      });
      // Same ordering guard as every other turn. A cached replay keeps its
      // original version, so re-pressing the button must not re-render the reply
      // a second time — which is exactly what the guard is for.
      if (!acceptResponse(res)) return res;
      // Present the returned wording once; preserve cue and scaffold as sent.
      addTranscriptMessage({ role: 'ai', text: res.message });
      const spoken = applyInteractionSupport(res);
      tutorSay(spoken, { afterMarks: Boolean(res.canvas_draw?.length) });
      if (res.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw);
      return res;
    } catch (err) {
      // Fall back ONLY when the endpoint genuinely is not there yet. A blanket
      // catch turned every real failure — a 500, an auth rejection, a timeout —
      // into a silent local replay, so the student saw the old cue reappear and
      // nobody ever learned the backend had failed.
      const status = (err as { response?: { status?: number } })?.response?.status;
      const endpointMissing = status === 404 || status === 405 || status === 422;
      if (endpointMissing) {
        console.warn('[explain-again] backend has no EXPLAIN_AGAIN yet — replaying the held cue');
        replayLocally();
        return null;
      }
      addTranscriptMessage({ role: 'ai', text: chatError(err, TUTOR_UNAVAILABLE) });
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Explain again failed.') });
      return null;
    }
  }, [sessionId, addTranscriptMessage, addTrailEntry]);

  /**
   * Reveal the next rung of the support ladder (§6).
   *
   * This used to POST /hint/request. That endpoint was deleted in the backend's
   * Schema 3.0 refactor (3 Aug 2026), so every press 404'd and the student was
   * told "no hint available" no matter what support the tutor had actually
   * authorised — the ladder looked broken when it was only unreachable.
   *
   * The rungs still arrive; they just arrive on the normal turn response now. So
   * this climbs what the backend has already authorised for the current question
   * instead of asking an endpoint that no longer exists.
   *
   * It is deliberately NOT a request for new support: only the Tutor Backend can
   * escalate a student up the ladder, and it needs an endpoint to do that (ask B1
   * in docs/PHASE2-GUIDED-BACKEND-ASKS.md). Until then this surfaces what is
   * there and says so plainly when there is nothing left.
   */
  const hint = useCallback(async (): Promise<SupportRung | null> => {
    const s = useNumeraStore.getState();
    const rung = nextSupport(
      s.supportShown,
      availableSupport({
        hintText: s.lastHintText,
        showVisualCue: Boolean(s.visualCueType ?? s.visualCueDescription),
        showScaffoldPanel: Boolean(s.activeScaffold),
        hasScaffoldStep: Boolean(s.activeScaffold?.stepText),
      }),
    );

    if (!rung) {
      addTranscriptMessage({ role: 'ai', text: LADDER_EXHAUSTED });
      return null;
    }

    s.setSupportShown(rung);
    if (rung === 'HINT' && s.lastHintText) {
      addTranscriptMessage({ role: 'ai', text: s.lastHintText });
      addTrailEntry({ kind: 'hint', text: s.lastHintText, meta: 'Hint' });
      tutorSay(s.lastHintText);
    } else if (rung === 'VISUAL_CUE') {
      s.setVisualCueVisible(true);
      if (s.visualCueDescription) tutorSay(s.visualCueDescription, { afterMarks: true });
    }
    // SCAFFOLD needs no reveal step: ScaffoldPanel renders whenever the backend
    // has authorised a step, so it is already on screen by the time we get here.
    return rung;
  }, [addTranscriptMessage, addTrailEntry]);

  /**
   * Fire one completed voice turn to the backend: snapshot the canvas, then send
   * the transcript + canvas reference through /interaction, and speak the reply.
   * This is the function the turn-end detector calls when the student stops.
   */
  const submitVoiceTurn = useCallback(
    async (
      transcript: string,
      ctx: { concept_id: string; current_phase: string; hint_count: number },
      confidence?: number
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId || !transcript.trim()) return null;
      // Overlap guard (contract §5): never submit while another turn is processing.
      if (useNumeraStore.getState().voiceStatus === 'processing') {
        console.warn('[voice] turn ignored — a previous turn is still processing');
        return null;
      }
      const questionId = useNumeraStore.getState().activeQuestionId;
      if (!questionId) {
        console.warn('[voice] turn ignored — no question is active in this phase');
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
          console.log('→ POST /canvas/submit', { session_id: sessionId, student_id: studentId(), snapshot_bytes: png.length });
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
          student_id: studentId(),
          interaction_type: 'ANSWER_SUBMISSION' as const,
          input_source: 'VOICE' as const,
          voice_transcript: transcript,
          transcript_confidence: confidence,
          canvas_snapshot_id: canvasSnapshotId,
          current_phase: state.currentPhase,
          concept_id: ctx.concept_id,
          question_id: questionId,
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
        // Ordering guard (handoff item 2), applied after the transport's own
        // stale/duplicate check: that one is about turn identity, this one is
        // about response ordering, and a reply can be fresh by one and stale by
        // the other.
        if (!acceptResponse(res)) {
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
        const spoken = applyInteractionSupport(res);
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
        // A scaffold response voices its one authorised step. Ordinary turns
        // voice the exact message shown in the transcript.
        tutorSay(spoken, {
          onEnd: () => {
            const store = useNumeraStore.getState();
            if (store.voiceStatus !== 'speaking') return; // superseded meanwhile
            if (expectsMore) store.beginListeningTurn();
            else store.setVoiceStatus('waiting');
          },
        });
        return res;
      } catch (err) {
        console.warn('✗ /interaction failed:', err);
        console.groupEnd();
        addTranscriptMessage({ role: 'ai', text: chatError(err, TUTOR_UNAVAILABLE) }); // surface the failure in the chat
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
    explainAgain,
    end,
  };
}
