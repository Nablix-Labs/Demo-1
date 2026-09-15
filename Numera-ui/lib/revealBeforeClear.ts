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
 *
 * ── Why the hold is no longer a constant ───────────────────────────────────
 *
 * It used to be a flat 900ms, picked as "long enough to read a short
 * annotation". That is long enough to READ one and not long enough to WRITE
 * one: `useTutorReveal` takes `max(700, chars × 95)`ms per text mark, so an
 * eighteen-character confirmation takes about 1.7s and a two-mark one nearly
 * four. The phase change landed at 900ms and cut the tutor off mid-word.
 *
 * That is issue #304 — "Tutor writes on canvas to confirm what the student said
 * but with out completing immediately moves to next question /sections" — which
 * reads as the backend advancing too early and is in fact this number.
 *
 * The hold now comes from `lib/tutorWritingTime.ts`, which is also what drives
 * the animation, so the two cannot disagree again.
 */

import { MAX_HOLD_MS } from '@/lib/tutorWritingTime';

export interface RevealDecision {
  /** Apply these against the question they describe, before anything clears. */
  reveal: boolean;
  /** Milliseconds to hold the board before the phase change lands. */
  holdMs: number;
}

/**
 * Should this reply's marks be shown before the phase change clears them, and
 * for how long?
 *
 * `writingMs` is what the tutor still owes on the board — see
 * `outstandingWritingMs`. Zero covers three different "nothing to wait for"
 * cases at once, which is why it is passed as a duration rather than a count:
 * no marks at all, marks that have already finished writing, and reduced
 * motion, where everything is drawn instantly.
 *
 * Held only when there is writing left AND the board is actually about to be
 * wiped. Holding the phase change on a turn that changes no question would
 * delay the next question for no reason, and holding it on a turn with nothing
 * being written would be a pause with nothing in it.
 */
export function revealDecision(
  writingMs: number,
  currentQuestionId: string | null,
  nextQuestionId: string | null | undefined,
): RevealDecision {
  const questionChanging =
    typeof nextQuestionId === 'string'
    && nextQuestionId.length > 0
    && currentQuestionId !== null
    && nextQuestionId !== currentQuestionId;

  const reveal = writingMs > 0 && questionChanging;
  return { reveal, holdMs: reveal ? Math.min(writingMs, MAX_HOLD_MS) : 0 };
}
