/**
 * Telling the backend the topic review is finished — exactly once.
 *
 * `REVIEW_COMPLETED` advances the Student Model's journey past Review, so it is
 * not a message to send casually. The review screen can be left more than one
 * way (three outcome buttons, plus the header's back-to-lesson), and a student
 * can return to it, so the naive "call it on the way out" fires repeatedly.
 *
 * The backend does dedupe — `_schema_request_id` is derived from the turn id, so
 * a repeat with the SAME turn id returns the stored session untouched. But we
 * mint a fresh turn id per call, which would defeat that entirely: every exit
 * would look like a new completion event. The guard therefore lives here, keyed
 * by session, and the turn id is minted once per session alongside it.
 */

/** Sessions already reported as reviewed, and the turn id used to report them. */
const reported = new Map<string, string>();

export interface ReviewCompletionPlan {
  /** Send it? False when there is nothing to report, or it has already gone. */
  send: boolean;
  /** The turn id to send — stable per session, so a retry stays idempotent. */
  turnId: string;
}

/**
 * Decide whether to report this session, and with which turn id.
 *
 * A missing session id is the ordinary demo/offline case, not an error: there
 * is no backend session to report against.
 */
export function planReviewCompletion(
  sessionId: string | null | undefined,
  mintTurnId: () => string,
): ReviewCompletionPlan {
  const id = sessionId?.trim();
  if (!id) return { send: false, turnId: '' };

  const already = reported.get(id);
  if (already) return { send: false, turnId: already };

  const turnId = mintTurnId();
  reported.set(id, turnId);
  return { send: true, turnId };
}

/**
 * Forget a session's completion.
 *
 * Only for a session that has genuinely gone (a new session id, or tests). NOT
 * called on failure: a failed report is still one attempt, and retrying on every
 * subsequent exit would send a completion event per button press.
 */
export function forgetReviewCompletion(sessionId?: string): void {
  if (sessionId) reported.delete(sessionId);
  else reported.clear();
}
