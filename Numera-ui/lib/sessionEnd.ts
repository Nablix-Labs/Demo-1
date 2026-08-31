/**
 * What /session/end must carry for the Review screen to open.
 *
 * Exactly one thing: a usable summary. This is a named function rather than two
 * lines inside the hook because the list of things it insists on is the list
 * that broke — and a guard inside a hook cannot be tested, so nothing failed
 * when it became wrong.
 *
 * It insisted on `session_review` until 18 Aug 2026. That field was deleted
 * from the backend outright (Sanya PR #155, "remove legacy session review
 * flow") because Phase 4 replaces it. Every /session/end after that merge threw
 * here, the Review screen read the throw as a failed end, and students who had
 * just finished a topic were told their review could not be loaded — for work
 * that had completed perfectly well.
 *
 * The rule this leaves behind: a field the backend stops sending must degrade
 * to "that part is not shown", never to "the screen failed". Only data the
 * screen genuinely cannot open without belongs in here.
 */

import { toSessionSummary, type SessionEndResponse, type SessionSummary } from '@/lib/api';
import { useNumeraStore } from '@/store/useNumeraStore';

export function sessionEndSummary(
  res: SessionEndResponse | null | undefined,
): SessionSummary {
  const summary = toSessionSummary(res);
  // No summary means no session came back at all — there is nothing to review
  // and the backend has left the session open, so this genuinely is a failure.
  if (!summary) throw new Error('Session ended but no summary was returned.');
  return summary;
}

/**
 * Land a finished session in the store.
 *
 * Here rather than inline in the hook for the reason the header above already
 * gives: this ordering broke and nothing failed, because a hook body cannot be
 * tested. `clearSessionId` also nulls `backendSession`
 * (store/useNumeraStore.ts:1059) — correct for its seven other callers, all of
 * which mean "this session is dead, drop it", and wrong for this one. The
 * Review screen reads `phase4_review` off that record on the very next render
 * (app/review/page.tsx:167), so the review painted once and then vanished.
 *
 * Clear the live-session state, then put the completed record back.
 */
export function storeEndedSession(
  res: SessionEndResponse,
  summary: SessionSummary,
): void {
  const store = useNumeraStore.getState();
  // Merged, not replaced: the record built up over the session carries the
  // question set and student-model state that the end response does not.
  const ended = { ...store.backendSession, ...res };
  // Remember WHICH session the review belongs to before clearSessionId drops
  // it, so a refresh on /review can fetch the record back. The id is the only
  // thing stored on the device; see NumeraState.endedSessionId.
  store.setEndedSessionId(res.session_id ?? store.sessionId);
  store.setSessionSummary(summary);
  if (res.session_review) store.setSessionReview(res.session_review);
  store.clearSessionId();
  store.setBackendSession(ended);
  // NOTE: this deliberately does NOT assert a phase.
  //
  // It used to `setCurrentPhase('REVIEW')` here, and that was right for the
  // shape the code had: /session/end returns the record with `current_phase`
  // UNCHANGED (session_service.py updates status, message and session_summary,
  // and nothing else), so the store still read INDEPENDENT_PRACTICE afterwards
  // and usePhaseRouting — which re-asserts the backend's phase on every screen
  // — pulled the student straight off /review back to /practice, where the last
  // question was still sitting. Manjusha, 29 Aug: "Why it's is taking me to
  // this question".
  //
  // That reasoning rested on "both callers of end() are on their way to
  // /review". They no longer are: entering Review does not end the session
  // (ending is not a phase transition), so end() now runs on the way OUT, after
  // REVIEW_COMPLETED. Asserting REVIEW there would push a student who has just
  // finished the review back onto /review and strand them.
  //
  // The assertion moved to app/practice/page.tsx's reviewWithTutor, which sets
  // it after READING the phase back from the backend — a verified fact rather
  // than one inferred from "a session ended". Manjusha's bug stays fixed; see
  // the comment there.
}
