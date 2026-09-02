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

/** Which step of the exit sequence failed, when one did. */
export type FinishStage = 'complete' | 'end';

export type FinishOutcome =
  | { ok: true }
  | { ok: false; stage: FinishStage; message: string };

/**
 * Leave the review: report REVIEW_COMPLETED, then end the session.
 *
 * Both failures are REPORTED. `/session/end` used to be called as
 * `await end().catch(() => undefined)` with the navigation running regardless,
 * so a failed end was indistinguishable from a successful one and the student
 * left on a session the backend never closed — with nothing on screen, and
 * nothing in any log, to say so.
 *
 * The old code's reasoning for swallowing it was not wrong: REVIEW_COMPLETED
 * has already landed by then, the phase HAS advanced, and stranding a student
 * over bookkeeping would be its own bug. What was wrong was the conclusion.
 * Reporting the failure and offering a retry costs the student one button; a
 * silent failure costs a session record nobody knows is missing. So the stage
 * is returned rather than a bare boolean: the caller can say which step needs
 * retrying, and can decide that a failed `end` is recoverable where a failed
 * `complete` is not.
 *
 * Ordered, and short-circuiting: ending first would mark the session done while
 * the event that closes the phase has not landed, so a failed completion never
 * reaches the end call.
 *
 * Safe to call again after a failure. `planReviewCompletion` memoises the turn
 * id per session and refuses a second send, so a retry re-attempts only the
 * step that failed and can never emit a second REVIEW_COMPLETED.
 */
export async function runReviewFinish(steps: {
  reportCompletion: () => Promise<void>;
  endSession: () => Promise<void>;
}): Promise<FinishOutcome> {
  try {
    await steps.reportCompletion();
  } catch (err) {
    return { ok: false, stage: 'complete', message: messageOf(err) };
  }
  try {
    await steps.endSession();
  } catch (err) {
    return { ok: false, stage: 'end', message: messageOf(err) };
  }
  return { ok: true };
}

function messageOf(err: unknown): string {
  return err instanceof Error && err.message ? err.message : 'Unknown error';
}
