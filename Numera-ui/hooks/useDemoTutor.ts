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
import { useCallback, useRef, useState } from 'react';
import {
  startSession,
  getSession,
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
  type InteractionPayload,
  type StaleTurnResponse,
  type NudgeDelivery,
  type QuestionType,
  isStaleTurnResponse,
  isStaleSessionError,
} from '@/lib/api';
import { applyInteractionSupport, acceptResponse } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { tutorSay, setStudentWriting } from '@/lib/tutorSpeech';
import { phaseAnnouncement, withTransitionVoice } from '@/lib/phaseTransition';
import { speakBrowser } from '@/lib/tts';
import type { SupportRung } from '@/lib/supportLadder';
import type { NudgeClaimResult } from '@/hooks/useInactivityNudge';
import { reportFailure } from '@/lib/failureReport';

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
 * Recover from a session the backend has forgotten.
 *
 * We keep the session id across reloads now (see the store's partialize), which
 * is what stops every refresh opening a second session on a topic already in
 * progress. The cost is that the id can outlive the backend, whose session
 * state is in memory and dies with the process — after a restart every call
 * answers 404 and the lesson would sit there failing forever.
 *
 * Clearing the id is enough: the lesson's start effect is guarded on it being
 * null, so dropping it is what asks for a fresh session. The latch has to go
 * too, or the retry is refused for the concept that just failed.
 *
 * Returns whether it recovered, so callers can skip their own error copy — a
 * dead session is not something to tell a student about when the next line of
 * code opens them a live one.
 */
export function recoverIfStaleSession(err: unknown): boolean {
  if (!isStaleSessionError(err)) return false;
  console.warn('[session] backend no longer has this session — starting a fresh one');
  resetSessionStart();
  useNumeraStore.getState().clearSessionId();
  return true;
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
  const res = (err as {
    response?: {
      status?: number;
      data?: { message?: string; error_code?: string; request_id?: string };
    };
  })?.response;
  if (res) {
    const parts = [`HTTP ${res.status ?? '?'}`];
    if (res.data?.error_code) parts.push(res.data.error_code);
    // The join key. The backend stamps request_id on every error and logs the
    // same id on its side, so quoting it here turns "it failed" into a line
    // anyone can grep straight to:
    //     journalctl -u nablix-backend | grep REQD6AA967B
    // Without it a tester reports a failure and someone else re-derives which
    // of the day's requests it was — which is most of the cost of a bug report.
    if (res.data?.request_id) parts.push(`req=${res.data.request_id}`);
    const detail = res.data?.message?.trim();
    return `${parts.join(' ')}${detail ? ` — ${detail}` : ''}`;
  }
  // No response object: the request genuinely never completed.
  return err instanceof Error ? `No response — ${err.message}` : fallback;
}

// Shown in the chat when a tutor call fails (e.g. backend 5xx), so a failure is
// visible to the student instead of the chat silently freezing.
const TUTOR_UNAVAILABLE = "Sorry — I couldn't reach the tutor just now. Please try again in a moment.";
const EXPLAIN_AGAIN_ACKNOWLEDGEMENT =
  'Okay—give me a moment. I’m looking at the question and the support already on your screen, so I can explain the same idea in a clearer, different way.';

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
 * Said instead of repeating an error the student has already been given.
 *
 * "Please try that again in a moment" is reasonable advice once. Said twice
 * verbatim it is worse than useless: the student cannot tell a second failure
 * from an echo of the first, and it keeps telling them to do the one thing that
 * has now demonstrably not worked (10 Aug — two identical bubbles, then a nudge
 * asking what they would try). The second time, stop asking them to retry and
 * say plainly that it is not them.
 */
const STILL_FAILING =
  'Still not working, and it is nothing you did — the problem is on my side. Retrying probably won’t help right now, so give it a few minutes or tell your teacher.';

/**
 * Record a failed tutor turn: one message in the chat, no duplicates, and the
 * inactivity controller told to stay quiet.
 *
 * Kept here rather than at each catch site because all four of them need the
 * same three things, and the nudge suppression is the part that is easy to
 * forget on a new one.
 */
function reportTutorFailure(
  err: unknown,
  fallback: string,
  add: (msg: { role: 'ai'; text: string }) => void,
  label = '/interaction',
): void {
  const store = useNumeraStore.getState();
  // Before anything student-facing: the full picture in the console, including
  // exactly what we sent. A screenshot of the chat says almost nothing; this
  // says who broke and gives the backend's own request_id to grep for.
  reportFailure(label, err, {
    session_id: store.sessionId,
    question_id: store.activeQuestionId,
    phase: store.currentPhase,
    turn_id: store.currentTurnId,
    previous_tutor_turn_id: store.lastTutorTurnId,
    expects_student_response: store.expectsStudentResponse,
  });
  const text = chatError(err, fallback);
  const previous = store.transcript.at(-1);
  const lastWasThisFailure = previous?.role === 'ai' && previous.text === text;
  const said = lastWasThisFailure ? STILL_FAILING : text;
  // Third failure onward the honest line has already been said, and repeating it
  // verbatim only makes the chat look broken on top of being broken. The trail
  // and the console still get every attempt.
  if (previous?.role !== 'ai' || previous.text !== said) add({ role: 'ai', text: said });
  // Whatever the student does next, they are owed a reply — not a nudge.
  store.markTutorTurnFailed();
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
export function syncBackendSession(response: {
  current_phase: string;
  current_question: string | null;
  question_id: string | null;
  question_number?: number;
  last_tutor_turn_id?: string | null;
  tutor_turn_id?: string | null;
  expected_student_response?: string;
  allow_voice_input?: boolean;
  /**
   * How the question expects to be answered. Present on both the session record
   * and every interaction reply, and until now read from neither — so a
   * CHOICE_WITH_EXPLANATION question rendered as free response, with its options
   * sitting unused on the record.
   */
  question_type?: QuestionType | null;
  inactivity_policy?: {
    initial_idle_threshold_ms: number;
    cooldown_ms: number;
    max_nudges_per_tutor_turn: number;
  };
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
    questionType: response.question_type ?? null,
  });
  if (response.question_number !== undefined) {
    store.setQuestionNumber(response.question_number);
  }
  const tutorTurnId = response.tutor_turn_id !== undefined
    ? response.tutor_turn_id
    : response.last_tutor_turn_id;
  if (tutorTurnId !== undefined) {
    store.setTutorTurn(tutorTurnId, {
      expects: response.expected_student_response !== 'NONE',
      allow: response.allow_voice_input ?? false,
    });
  }

  // Progress rail (§2). The denominator only exists on the session record's
  // question set, so this is the one place both halves are known at once.
  const { index, total } = questionProgress(store.backendSession, response.question_id);
  store.setQuestionProgress(index, total);
  if (response.inactivity_policy) {
    store.setInactivityPolicy({
      initialIdleThresholdMs: response.inactivity_policy.initial_idle_threshold_ms,
      cooldownMs: response.inactivity_policy.cooldown_ms,
      maxNudgesPerTutorTurn: response.inactivity_policy.max_nudges_per_tutor_turn,
    });
  }
}

class TurnSynchronizationError extends Error {
  constructor(sessionId: string, turnId: string | undefined) {
    super(
      `Tutor turn synchronization failed after one retry for session_id=${sessionId} `
      + `turn_id=${turnId ?? 'missing'}.`,
    );
    this.name = 'TurnSynchronizationError';
  }
}

function synchronizeStaleTurn(response: StaleTurnResponse): void {
  const store = useNumeraStore.getState();
  store.setTutorTurn(response.expected_previous_tutor_turn_id, {
    expects: true,
    allow: store.allowVoiceInput,
  });
}

/**
 * Submit one student-owned interaction against the latest tutor turn.
 *
 * A stale response is authoritative reconciliation data, not tutor feedback.
 * The backend did not evaluate the turn, so retrying the same idempotency key
 * once with its expected pointer is safe and prevents the student losing work.
 */
export async function sendSynchronizedInteraction(
  payload: InteractionPayload,
): Promise<InteractionResponse> {
  const first = await sendInteraction(payload);
  if (!isStaleTurnResponse(first)) return first;

  synchronizeStaleTurn(first);
  const retried = await sendInteraction({
    ...payload,
    previous_tutor_turn_id: first.expected_previous_tutor_turn_id,
  });
  if (isStaleTurnResponse(retried)) {
    synchronizeStaleTurn(retried);
    throw new TurnSynchronizationError(payload.session_id, payload.turn_id);
  }
  return retried;
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
      // A failed start is the most consequential failure in the app — nothing
      // else works after it — and until now it left one trail entry the student
      // never sees. The 401 here is the anon-bearer wall: the tutor backend
      // accepts the placeholder, then forwards SESSION_OPENED to student_model,
      // which validates it properly and rejects (INVALID_TOKEN).
      reportFailure('/session/start', err, { concept_id: conceptId, mode });
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

let resumeInFlight: Promise<void> | null = null;

let systemTurnSequence = 0;

function nextSystemTurnId(kind: 'NUDGE' | 'NUDGE-ACK'): string {
  systemTurnSequence += 1;
  return `${kind}-${Date.now()}-${systemTurnSequence}`;
}

/**
 * Rehydrate a persisted session after a page refresh.
 *
 * `sessionId` survives the refresh (persist/partialize) but `backendSession`,
 * the question and the phase do not — and `beginSession` short-circuits on the
 * surviving id. The lesson therefore came back BLANK: no question on the
 * canvas, no opening message, and every REST turn dropped with "no question is
 * active". GET /session/{id} has existed in lib/api.ts the whole time with no
 * caller; this is its caller. A 404 means the backend has forgotten the
 * session (restart) — drop it so a fresh one starts.
 */
export async function resumeSession(): Promise<void> {
  if (!apiEnabled()) return;
  const store = useNumeraStore.getState();
  if (!store.sessionId || store.backendSession) return;
  if (resumeInFlight) return resumeInFlight;
  resumeInFlight = (async () => {
    try {
      const rec = await getSession(store.sessionId!);
      const s = useNumeraStore.getState();
      s.setBackendSession(rec);
      syncBackendSession(rec);
      if (s.transcript.length === 0) {
        const restored = (rec.conversation_history ?? []).map((message) => ({
          role: message.role === 'user' ? 'student' as const : 'ai' as const,
          text: message.content,
        }));
        if (restored.length > 0) {
          s.setTranscript(restored);
        } else if (rec.message.trim()) {
          s.setTranscript([{ role: 'ai', text: rec.message }]);
        }
      }
      // Say where we are, out loud, on every resume.
      //
      // A resumed session restored the conversation silently: the student came
      // back to a wall of text and a tutor that said nothing, on a voice-first
      // product (Sanya, 11 Aug — "we need it spoken on every session resume").
      // Only the CURRENT line is spoken, never the restored history — replaying
      // a whole conversation aloud would be worse than saying nothing.
      if (rec.message.trim()) {
        useNumeraStore.getState().setPendingTutorSpeech(rec.message.trim());
      }
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (isStaleSessionError(err) || status === 404) {
        resetSessionStart();
        useNumeraStore.getState().clearSessionId();
      } else {
        console.warn('✗ session resume failed (will stay on the stored session):', err);
      }
    } finally {
      resumeInFlight = null;
    }
  })();
  return resumeInFlight;
}

export function useDemoTutor() {
  const sessionId = useNumeraStore((s) => s.sessionId);
  const canvasExporter = useNumeraStore((s) => s.canvasExporter);
  const canvasSubmissionInFlight = useRef(false);
  const explainAgainRequest = useRef<Promise<InteractionResponse | null> | null>(null);
  const [explainAgainPending, setExplainAgainPending] = useState(false);
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
        const res = await sendSynchronizedInteraction({
          session_id: sessionId,
          student_id: studentId(),
          interaction_type: 'ANSWER_SUBMISSION',
          input_source: 'TEXT',
          text_input: text,
          // Tell the tutor WHICH option was picked, in every phase.
          //
          // The Phase 3 confirmation payloads that used to gate this were
          // removed in 2950941; the gate variable went with them and left this
          // line referring to a name that no longer exists, so main did not
          // compile. Sending the id whenever there is one is also what row 23
          // asks for — without it the tutor sees the option's text and has no
          // idea which choice it corresponds to.
          selected_option_id: state.selectedOptionId ?? undefined,
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
        // Read the phase we were in BEFORE advancing it, or the transition can
        // never be detected.
        const entering = phaseAnnouncement(res, useNumeraStore.getState().currentPhase);
        if (entering) {
          addTranscriptMessage({ role: 'ai', text: entering.text });
          addTrailEntry({ kind: 'tutor', text: entering.text, meta: 'phase change' });
        }
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        if (res.current_phase) useNumeraStore.getState().setCurrentPhase(res.current_phase); // advance phase
        const drew = Boolean(res.canvas_draw?.length);
        if (drew) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw!);
        const spoken = withTransitionVoice(entering, applyInteractionSupport(res));
        // §1: highlight first, pause, then speak. When the turn also drew, the
        // mark lands before it is described; when it didn't, this speaks at once.
        tutorSay(spoken, { afterMarks: drew });
        return res;
      } catch (err) {
        if (recoverIfStaleSession(err)) return null;
        reportTutorFailure(err, TUTOR_UNAVAILABLE, addTranscriptMessage, '/interaction (answer)');
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Tutor unavailable.') });
        return null;
      }
    },
    [sessionId, addTranscriptMessage, addTrailEntry]
  );

  /** Export the current canvas and submit it for live OCR + tutor feedback. */
  const submitCanvasWork = useCallback(async (): Promise<CanvasSubmissionResult | null> => {
    if (!apiEnabled() || !sessionId) return null;
    const canvasSnapshot = hasCanvasActivity() ? canvasExporter?.() : null;
    if (!canvasSnapshot) {
      const message = 'Write or draw something on the canvas first, then I can check it with you.';
      addTranscriptMessage({ role: 'ai', text: message });
      addTrailEntry({ kind: 'tutor', text: message });
      return null;
    }
    if (canvasSubmissionInFlight.current) return null;
    canvasSubmissionInFlight.current = true;
    try {
      const res = await submitCanvas(sessionId, canvasSnapshot.snapshotDataUrl, 'STANDALONE_ATTEMPT');
      // Canvas responses now carry the same phase state as /interaction, so a
      // backend phase change here also drives usePhaseRouting.
      const entering = phaseAnnouncement(res, useNumeraStore.getState().currentPhase);
      if (res.current_phase) {
        syncBackendSession({
          current_phase: res.current_phase,
          current_question: res.current_question ?? null,
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
      if (entering) {
        addTranscriptMessage({ role: 'ai', text: entering.text });
        addTrailEntry({ kind: 'tutor', text: entering.text, meta: 'phase change' });
      }
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
      tutorSay(withTransitionVoice(entering, res.tutor.tutor_message), { afterMarks: drew });
      return res;
    } catch (err) {
      // A forgotten session recovers by opening a new one; see
      // recoverIfStaleSession. Nothing to report to the student.
      if (recoverIfStaleSession(err)) return null;
      reportTutorFailure(err, TUTOR_UNAVAILABLE, addTranscriptMessage, '/canvas/submit');
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not read the canvas.') });
      return null;
    } finally {
      canvasSubmissionInFlight.current = false;
    }
  }, [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]);

  /**
   * Explain Again — replay the current explanation.
   *
   * Neither an answer nor a help escalation (Phase 2 handoff, Manav — Frontend,
   * Explain Again 2). The frontend computes nothing: no attempts, no components,
   * no support progression and no scaffold changes. It immediately acknowledges
   * the request, then renders the generated explanation when it arrives.
   *
   * Older deployments can still return 404/405/422; only those explicit
   * compatibility responses fall back to the cue already held by the client.
   */
  const runExplainAgain = useCallback(async (): Promise<InteractionResponse | null> => {
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
    addTranscriptMessage({ role: 'ai', text: EXPLAIN_AGAIN_ACKNOWLEDGEMENT });
    addTrailEntry({ kind: 'tutor', text: EXPLAIN_AGAIN_ACKNOWLEDGEMENT });
    // Explain Again is an explicit handoff from the student to the tutor, even
    // when the canvas still contains unsubmitted marks.
    setStudentWriting(false);
    const acknowledgementFinished = new Promise<void>((resolve) => {
      tutorSay(EXPLAIN_AGAIN_ACKNOWLEDGEMENT, {
        onEnd: resolve,
        // This acknowledgement must begin on the click itself. Waiting for a
        // remote TTS round trip makes it arrive alongside the LLM explanation,
        // which defeats its purpose and can lose browser audio permission.
        speak: speakBrowser,
      });
    });
    const acknowledgementWindow = Promise.race([
      acknowledgementFinished,
      new Promise<void>((resolve) => window.setTimeout(resolve, 6000)),
    ]);
    try {
      const res = await sendSynchronizedInteraction({
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
      if (!acceptResponse(res)) {
        await acknowledgementWindow;
        return res;
      }
      syncBackendSession(res);
      // Present the returned wording once; preserve cue and scaffold as sent.
      await acknowledgementWindow;
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
        await acknowledgementWindow;
        console.warn('[explain-again] backend has no EXPLAIN_AGAIN yet — replaying the held cue');
        replayLocally();
        return null;
      }
      // A failed API call must release the button immediately. Speech engines
      // do not consistently fire onEnd when playback is muted or interrupted;
      // waiting here previously left Explain Again stuck on "Explaining…".
      reportTutorFailure(err, TUTOR_UNAVAILABLE, addTranscriptMessage, '/interaction (explain again)');
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Explain again failed.') });
      return null;
    }
  }, [sessionId, addTranscriptMessage, addTrailEntry]);

  const explainAgain = useCallback((): Promise<InteractionResponse | null> => {
    if (explainAgainRequest.current !== null) return explainAgainRequest.current;
    setExplainAgainPending(true);
    const request = runExplainAgain().finally(() => {
      explainAgainRequest.current = null;
      setExplainAgainPending(false);
    });
    explainAgainRequest.current = request;
    return request;
  }, [runExplainAgain]);

  const claimInactivityNudge = useCallback(async (
    idleDurationMs: number,
  ): Promise<NudgeClaimResult> => {
    const state = useNumeraStore.getState();
    if (!apiEnabled() || !sessionId || !state.activeQuestionId) {
      return { status: 'SUPPRESSED' };
    }
    const turnId = nextSystemTurnId('NUDGE');
    const res = await sendInteraction({
      session_id: sessionId,
      student_id: studentId(),
      interaction_type: 'INACTIVITY_NUDGE',
      input_source: 'SYSTEM',
      turn_id: turnId,
      previous_tutor_turn_id: state.lastTutorTurnId,
      idle_duration_ms: idleDurationMs,
      current_phase: state.currentPhase,
      concept_id: state.activeConceptId,
      question_id: state.activeQuestionId,
      hint_count: state.lastHintText ? 1 : 0,
    });
    if (isStaleTurnResponse(res)) {
      synchronizeStaleTurn(res);
      return { status: 'OUT_OF_SYNC' };
    }
    if (res.status === 'DUPLICATE_TURN') {
      if (res.tutor_turn_id !== undefined) {
        useNumeraStore.getState().setTutorTurn(res.tutor_turn_id, {
          expects: res.expects_student_response ?? true,
          allow: res.allow_voice_input ?? state.allowVoiceInput,
        });
      }
      return { status: 'OUT_OF_SYNC' };
    }
    if (res.status === 'NUDGE_SUPPRESSED' || !res.nudge_delivery) {
      return { status: 'SUPPRESSED' };
    }
    return { status: 'DELIVERED', delivery: res.nudge_delivery };
  }, [sessionId]);

  /**
   * Deliver an authorised nudge: one chat line, spoken once.
   *
   * It has to land in the transcript as well as the speaker. Speaking it alone
   * meant a voice arrived with nothing on screen to account for it — the
   * student hears the tutor start talking and there is no message anywhere
   * explaining why, which is how it read in testing ("the tutor starts speaking
   * randomly", Sanya, 5 Aug). A line the student can see and scroll back to is
   * a nudge; a disembodied voice is an interruption.
   *
   * Still not a tutor turn: no turn ids, no support state, no trail entry,
   * because the student has not done anything to respond to.
   */
  const presentInactivityNudge = useCallback(
    (delivery: NudgeDelivery): void => {
      addTranscriptMessage({ role: 'ai', text: delivery.message });
      tutorSay(delivery.message, { afterMarks: true });
    },
    [addTranscriptMessage],
  );

  const acknowledgeInactivityNudge = useCallback(
    async (delivery: NudgeDelivery): Promise<void> => {
      const state = useNumeraStore.getState();
      if (!apiEnabled() || !sessionId || !state.activeQuestionId) return;
      const res = await sendInteraction({
        session_id: sessionId,
        student_id: studentId(),
        interaction_type: 'NUDGE_PRESENTED',
        input_source: 'SYSTEM',
        turn_id: nextSystemTurnId('NUDGE-ACK'),
        previous_tutor_turn_id: state.lastTutorTurnId,
        nudge_id: delivery.interaction_id,
        current_phase: state.currentPhase,
        concept_id: state.activeConceptId,
        question_id: state.activeQuestionId,
        hint_count: state.lastHintText ? 1 : 0,
      });
      if (isStaleTurnResponse(res)) {
        synchronizeStaleTurn(res);
        throw new TurnSynchronizationError(sessionId, undefined);
      }
      if (res.nudge_delivery?.status !== 'PRESENTED') {
        throw new Error('Backend did not acknowledge the presented inactivity nudge.');
      }
      addTrailEntry({ kind: 'tutor', text: delivery.message, meta: 'inactivity nudge' });
    },
    [sessionId, addTrailEntry],
  );

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
    if (!apiEnabled() || !sessionId || !s.activeQuestionId) {
      return null;
    }
    const turnId = s.beginSubmissionTurn();
    const res = await sendSynchronizedInteraction({
      session_id: sessionId,
      student_id: studentId(),
      interaction_type: 'HELP_REQUEST',
      input_source: 'TEXT',
      text_input: 'Please give me the next hint.',
      current_phase: s.currentPhase,
      concept_id: s.activeConceptId,
      question_id: s.activeQuestionId,
      hint_count: s.lastHintText ? 1 : 0,
      turn_id: turnId,
      previous_tutor_turn_id: s.lastTutorTurnId,
    });
    if (!acceptResponse(res)) return null;
    syncBackendSession(res);
    addTranscriptMessage({ role: 'ai', text: res.message });
    addTrailEntry({ kind: 'hint', text: res.message, meta: res.support_served_this_turn ?? 'support' });
    const spoken = applyInteractionSupport(res);
    tutorSay(spoken, { afterMarks: Boolean(res.canvas_draw?.length) });
    const served = res.support_served_this_turn;
    const rung: SupportRung | null = served && served !== 'NONE' ? served : null;
    if (rung) useNumeraStore.getState().setSupportShown(rung);
    return rung;
  }, [sessionId, addTranscriptMessage, addTrailEntry]);

  /**
   * Fire one completed voice turn to the backend with one frozen canvas payload,
   * then speak the reply.
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
      const canvasSnapshot = canvasExporter?.();
      if (!canvasSnapshot) {
        const message = 'I could not capture the board for this voice turn. Please try again.';
        addTranscriptMessage({ role: 'ai', text: message });
        addTrailEntry({ kind: 'tutor', text: message });
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

      try {
        const state = useNumeraStore.getState();
        const interactionReq = {
          session_id: sessionId,
          student_id: studentId(),
          interaction_type: 'ANSWER_SUBMISSION' as const,
          input_source: 'VOICE' as const,
          voice_transcript: transcript,
          transcript_confidence: confidence,
          canvas_state: {
            snapshot_data_url: canvasSnapshot.snapshotDataUrl,
            strokes: canvasSnapshot.strokes,
            captured_at: canvasSnapshot.capturedAt,
          },
          current_phase: state.currentPhase,
          concept_id: ctx.concept_id,
          question_id: questionId,
          hint_count: ctx.hint_count,
          // Voice turn-sync contract (§5): identify the turn so the backend can
          // dedupe/reject stale turns. transcript_final is always true here.
          //
          // Mint one rather than sending `undefined`. turn_id is REQUIRED on
          // InteractionRequest (interaction.py:57), so omitting it is a 422
          // before the tutor ever sees the answer — the same shape of failure
          // as the nudge's null previous_tutor_turn_id and the voice socket's
          // missing turn_id, both found today.
          //
          // It can genuinely be null here: this path reads the id but never
          // opens a turn, and the only opener on entry is page.tsx, which skips
          // it when the session starts already in GUIDED_PRACTICE. A student
          // resuming straight into guided practice whose opening line never
          // finished speaking would answer with no turn id at all.
          turn_id: state.currentTurnId ?? state.beginSubmissionTurn(),
          previous_tutor_turn_id: state.lastTutorTurnId,
          transcript_final: true,
        };
        console.log('→ POST /interaction', interactionReq);
        const res = await sendSynchronizedInteraction(interactionReq);
        console.log('← /interaction', res);
        // A newer turn fired while we were waiting — drop this stale reply so it
        // can't append out of order under the wrong student turn.
        if (myTurn !== voiceTurnSeq) {
          console.log('(superseded by a newer turn — reply dropped)');
          console.groupEnd();
          return null;
        }
        // A duplicate is a cached response and the ordering gate below decides
        // whether it has already been rendered. STALE_TURN is reconciled and
        // retried inside sendSynchronizedInteraction before reaching here.
        if (res.status === 'DUPLICATE_TURN') {
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
        const entering = phaseAnnouncement(res, useNumeraStore.getState().currentPhase);
        if (entering) {
          addTranscriptMessage({ role: 'ai', text: entering.text });
          addTrailEntry({ kind: 'tutor', text: entering.text, meta: 'phase change' });
        }
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        if (res.ocr) {
          addTrailEntry({
            kind: 'canvas',
            text: res.ocr.raw_ocr_text || res.ocr.detected_equation || 'Canvas submitted.',
            meta: `OCR ${(res.ocr.confidence * 100).toFixed(0)}%`,
          });
        }
        if (res.current_phase) useNumeraStore.getState().setCurrentPhase(res.current_phase); // advance phase
        if (res.canvas_draw?.length) useNumeraStore.getState().applyCanvasDraw(res.canvas_draw);
        const spoken = withTransitionVoice(entering, applyInteractionSupport(res));
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
        // The backend has forgotten this session (its state is in memory).
        // Clearing the id makes the lesson open a fresh one, so there is
        // nothing here worth telling the student about.
        if (recoverIfStaleSession(err)) {
          useNumeraStore.getState().beginListeningTurn();
          return null;
        }
        reportTutorFailure(err, TUTOR_UNAVAILABLE, addTranscriptMessage, '/interaction (voice turn)');
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
    explainAgainPending,
    claimInactivityNudge,
    presentInactivityNudge,
    acknowledgeInactivityNudge,
    end,
  };
}
