/**
 * When the student may enter Review, and what a refused Review looks like.
 *
 * Two rules that were previously inlined as conditions in two different
 * components, and drifted apart:
 *
 *   1. Review is a BACKEND phase, not a screen the student can ask for. The
 *      only automatic exit from Independent Practice is full mastery, so a
 *      button offered on "the current question is locked" promises a
 *      transition the backend has not made and will not make on request.
 *
 *   2. A review that failed to generate is not an empty review. The backend
 *      answers 200 with no review on the way in (so the client still learns
 *      its session_id, which is the argument to the retry) and refuses the
 *      read with PHASE4_REVIEW_UNAVAILABLE until one exists.
 *
 * Named rather than inlined for the reason lib/reviewContent.ts gives about
 * itself: a guard inside a component cannot be tested, so nothing fails when
 * it becomes wrong.
 */

/** The backend's machine-readable "generation failed, ask again" code. */
export const REVIEW_UNAVAILABLE = 'PHASE4_REVIEW_UNAVAILABLE';

/** One session, as much of it as these rules read. */
export interface ReviewReadySession {
  current_phase?: string | null;
  phase4_review?: unknown;
}

/**
 * True only when the backend is in Review AND has a review to show.
 *
 * Both halves are required. `current_phase === 'REVIEW'` alone is the state a
 * failed generation leaves behind, and entering on it renders the screen with
 * nothing on it — the original bug.
 */
export function reviewIsReady(
  session: ReviewReadySession | null | undefined,
): boolean {
  if (!session) return false;
  if (session.current_phase?.trim().toUpperCase() !== 'REVIEW') return false;
  return session.phase4_review !== null && session.phase4_review !== undefined;
}

/**
 * True when the backend refused the read because the review is not prepared.
 *
 * Matches on `error_code`, which the backend lifts out of the exception's
 * `{code, message}` detail. Deliberately not a substring match on the message:
 * that is student-facing prose and may be reworded.
 */
export function isReviewUnavailable(error: unknown): boolean {
  const body = (error as { response?: { data?: { error_code?: unknown } } })
    ?.response?.data;
  return body?.error_code === REVIEW_UNAVAILABLE;
}
