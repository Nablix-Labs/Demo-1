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
 * Was the engine unreachable part-way through moving the student on?
 *
 * `503 PROGRESSION_RETRY_REQUIRED`. Retryable and safe, which is the unusual
 * part: the follow-up event is already persisted, so a retry re-sends the
 * identical event and nothing is graded or counted twice
 * (`session_service.py:2020`). The answer is NOT resubmitted and this is not a
 * failed attempt — the student's work is saved and the only thing that failed
 * was the progression.
 *
 * It can come back from GET /session itself, which is the one route the client
 * is told to call to recover, so a read that fails this way must be retried
 * rather than treated as a dead end. Matched on the code, never the bare 503: a
 * plain 503 is not known to be safe to retry, and retrying one blindly is how a
 * client doubles an attempt.
 */
export function isProgressionRetryRequired(err: unknown): boolean {
  const res = (err as { response?: { status?: number; data?: { error_code?: string } } })?.response;
  return res?.status === 503 && res?.data?.error_code === 'PROGRESSION_RETRY_REQUIRED';
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

/** Blank and whitespace-only ids identify nothing; treat them as absent. */
function named(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

/**
 * Does this response still belong to the session and topic on screen?
 *
 * The topic transition is where late replies bite. Review completes, the client
 * opens the next topic, and an in-flight Review reply — or a GET for the OLD
 * session — lands afterwards. Applied, it drags the student back to a topic
 * they have finished, and because it carries a real phase and a real question
 * nothing downstream can tell it is history.
 *
 * The turn-ordering guard already in place cannot catch these: it compares
 * turns WITHIN a session, and a late reply is perfectly ordered by that
 * measure. It is wrong by identity, not by order.
 *
 * Judged only on the fields the response actually carries. A response naming
 * neither is accepted rather than dropped — a backend that stops sending a
 * field must degrade, not black out the screen — and so is anything arriving
 * before a session is active, which is how a session's own first reply lands.
 */
export function belongsToActiveSession(
  res: { session_id?: string | null; concept_id?: string | null },
  active: { sessionId: string | null; topicId: string | null },
): boolean {
  const session = named(res.session_id);
  const activeSession = named(active.sessionId);
  if (session && activeSession && session !== activeSession) return false;

  const topic = named(res.concept_id);
  const activeTopic = named(active.topicId);
  if (topic && activeTopic && topic !== activeTopic) return false;

  return true;
}
