/**
 * Recovering from a conflict, without grading work against a question nobody
 * asked.
 *
 * The live ST010 run went: a 503 after Student Model had already accepted a
 * failed checkpoint, then a journey-version conflict, then the student's ink
 * for the OLD question submitted against a newly selected one. The last step is
 * the one that corrupted evidence, and it is why recovery is now explicit
 * rather than something each catch site improvises.
 *
 * The sequence the backend requires (frontend handoff, 9 Sep 2026):
 *
 *   1. On a conflict, stop submitting. The stale question, its answer
 *      specification and its presentation state have all been invalidated
 *      together, and the session is marked as needing recovery.
 *   2. Do NOT re-POST. It is refused with SESSION_STATE_REFRESH_REQUIRED —
 *      deliberately, because recovery is what selects the authoritative
 *      question and a submission already in flight would be graded against a
 *      question the student never saw.
 *   3. GET /session — this is what performs the recovery. It returns 200 with
 *      the restored phase, question and flags, and grades nothing.
 *   4. Compare identity before re-enabling Check.
 *
 * This module owns steps 1 and 4 — the two decisions. The GET and the store
 * changes live at the call site; keeping the decisions pure is what makes them
 * testable without a session.
 *
 * ── One field short of the contract ──────────────────────────────────────────
 *
 * The handoff asks for identity on four fields: session, topic, `question_id`
 * and `question_usage_id`. Only three are available. `question_usage_id` is not
 * on the session record — on either side of the wire. In the backend it exists
 * only on the Phase 4 and work-artifact models (`phase4_review.py`,
 * `work_artifact.py`, `topic_event_history.py`), never on `SessionRecord`, so
 * `GET /session` cannot return it and this module cannot compare it.
 *
 * That gap matters in one specific case: the same `question_id` re-served as a
 * NEW usage — which is exactly what a Guided repair return is
 * (RESUME_SAME_INDEPENDENT_QUESTION re-serves the same question id). There, the
 * three fields compare equal while the usage has in fact changed. That is
 * survivable here only because a repair return is not a conflict recovery and
 * arrives through `phase3Routing` instead; it is NOT a reason to relax the
 * guard. Asking for `question_usage_id` on the session record is a backend ask,
 * not something to infer client-side — inferring it would be the client
 * re-deciding question identity, which is the whole failure this guards.
 */

import type { SessionRecord } from '@/lib/api';

/** The 409s that mean "recover", as opposed to the 409s that mean other things. */
const REFRESH_REQUIRED_CODES = new Set([
  // The stale question was invalidated under us.
  'JOURNEY_VERSION_CONFLICT',
  // We submitted anyway (or a retry did) and the backend refused it.
  'SESSION_STATE_REFRESH_REQUIRED',
]);

/**
 * Does this failure require a mandatory session refresh before any submission?
 *
 * Matched on `error_code` AND the 409, never on either alone. /interaction
 * returns 409 for an intervention pause and for a content gap too, and both
 * have their own screens — recovering them as conflicts would replace a paused
 * screen with a live question. The status is checked as well because the same
 * code on a 500 is a server fault, and refreshing past it would hide it.
 */
export function requiresSessionRefresh(err: unknown): boolean {
  const res = (err as { response?: { status?: number; data?: { error_code?: string } } })?.response;
  if (res?.status !== 409) return false;
  return REFRESH_REQUIRED_CODES.has(res?.data?.error_code ?? '');
}

/**
 * What the student's pending work is pinned to.
 *
 * Three fields, not four — see the header for why `question_usage_id` is
 * missing and why it is not inferred.
 */
export interface SubmissionIdentity {
  sessionId: string | null;
  topicId: string | null;
  /** Null on any phase without a question of its own, e.g. orientation. */
  questionId: string | null;
}

/** The identity a session record describes. */
export function identityOf(rec: SessionRecord): SubmissionIdentity {
  return {
    sessionId: rec.session_id ?? null,
    topicId: rec.concept_id ?? null,
    questionId: rec.question_id ?? null,
  };
}

/**
 * May the work held for `before` be submitted against what recovery returned?
 *
 * A missing question is never a match, on either side. Two nulls in particular
 * are not evidence of sameness — neither names a question, so there is nothing
 * for the ink to be an answer to, and treating that as "unchanged" would
 * re-enable Check on a screen with no question on it.
 */
export function identityMatches(before: SubmissionIdentity, after: SubmissionIdentity): boolean {
  if (before.questionId == null || after.questionId == null) return false;
  return before.sessionId === after.sessionId
    && before.topicId === after.topicId
    && before.questionId === after.questionId;
}
