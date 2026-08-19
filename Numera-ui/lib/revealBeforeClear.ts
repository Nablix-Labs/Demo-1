/**
 * Letting the tutor's last marks be seen before the board is wiped.
 *
 * A Guided Practice reply that completes the question does two things at once:
 * it annotates the work the student just finished, and it moves them on. Applied
 * in that order the annotation never exists — `applyBackendPhase` clears the
 * canvas, the anchors and the tutor layer the moment the question id changes,
 * so the marks are wiped in the same tick they were added and the student sees
 * the board blank rather than the point being made.
 *
 * Worse, the ordering also put this turn's actions against the NEXT question's
 * anchors, which is the one thing Sanya's handoff calls out by name. The
 * resolver drops them rather than misplacing them, so the failure was silent
 * instead of wrong — but silent is still the tutor going quiet exactly when it
 * had something to say.
 *
 * So: apply the marks against the question they describe, hold them briefly,
 * then let the phase change land.
 */

/**
 * How long the completed question's marks stay up before the board clears.
 *
 * Long enough to read a short annotation and connect it to the work it points
 * at; short enough that it reads as the end of the turn rather than a stall.
 * Deliberately the same order as the transition dwell the diagnostic already
 * uses for its tutor lines (MIN_DWELL, 900ms) — the two are the same kind of
 * pause and should not feel different.
 */
export const REVEAL_MS = 900;

export interface RevealDecision {
  /** Apply these against the question they describe, before anything clears. */
  reveal: boolean;
  /** Milliseconds to hold the board before the phase change lands. */
  holdMs: number;
}

/**
 * Should this reply's marks be shown before the phase change clears them?
 *
 * Only when there is something to show AND the board is actually about to be
 * wiped. Holding the phase change on a turn that changes no question would
 * delay the next question for no reason, and holding it on a turn with no marks
 * would be a pause with nothing in it.
 */
export function revealDecision(
  actionCount: number,
  currentQuestionId: string | null,
  nextQuestionId: string | null | undefined,
): RevealDecision {
  const questionChanging =
    typeof nextQuestionId === 'string'
    && nextQuestionId.length > 0
    && currentQuestionId !== null
    && nextQuestionId !== currentQuestionId;

  const reveal = actionCount > 0 && questionChanging;
  return { reveal, holdMs: reveal ? REVEAL_MS : 0 };
}
