/**
 * The scaffold steps the student has already been shown.
 *
 * The backend releases ONE step at a time and says so in the contract: the
 * reply carries `scaffold_step_text` for the current step and
 * `total_scaffold_steps` as "a progress indicator, NOT permission to reveal
 * later ones" (lib/api.ts). So a margin that lists the whole scaffold cannot
 * be built from one reply — and must never be built by guessing the rest.
 *
 * What IS allowed is remembering. A step the tutor has already put on screen
 * has been revealed; keeping it visible afterwards reveals nothing new, and
 * it is what turns "Step 2 of 4" from a bare counter into a path the student
 * can see themselves walking. That is the whole of this module: it accumulates
 * what has been shown, and it never invents what has not.
 *
 * Steps AHEAD of the current one are rendered by the margin as bare numbers,
 * with no text, for the same reason — the count is public, the wording is not.
 */

import type { ActiveScaffold } from '@/lib/api';

export interface SeenScaffoldStep {
  stepId: string;
  stepNumber: number;
  stepText: string;
}

const stepOf = (s: ActiveScaffold): SeenScaffoldStep => ({
  stepId: s.currentStepId,
  stepNumber: s.stepNumber,
  stepText: s.stepText,
});

/**
 * Fold the arriving step into the trail.
 *
 * `previous`/`next` are the store's `activeScaffold` before and after this
 * turn. The trail INCLUDES the current step, so the margin renders one list
 * and marks the current entry rather than concatenating two.
 *
 * Closing the panel (`next` null) empties it. A closed scaffold is finished —
 * the next one to open is a different piece of teaching, and carrying the old
 * trail into it would caption the new question with the old question's steps.
 * The margin does not render at all while it is closed, so nothing is lost on
 * screen by clearing here rather than later.
 */
export function rememberScaffoldStep(
  seen: SeenScaffoldStep[],
  previous: ActiveScaffold | null,
  next: ActiveScaffold | null,
): SeenScaffoldStep[] {
  if (!next) return [];
  // A different scaffold is a different ladder; its first step starts a trail.
  if (!previous || previous.scaffoldId !== next.scaffoldId) return [stepOf(next)];

  // Re-sent rather than advanced — the backend repeats the current step on a
  // turn that did not move on. Take the newer wording, do not add a row.
  if (seen.some((s) => s.stepId === next.currentStepId)) {
    return seen.map((s) => (s.stepId === next.currentStepId ? stepOf(next) : s));
  }

  // Ordered by the backend's own step number rather than by arrival, so a step
  // re-opened out of order still reads down the margin in teaching order.
  return [...seen, stepOf(next)].sort((a, b) => a.stepNumber - b.stepNumber);
}

/**
 * The rows the margin draws: every step of the scaffold, in order.
 *
 * `pending` rows carry no text — see the header. They exist so the student can
 * see how much is left, which is exactly what `totalSteps` is for.
 */
export type TrailRow =
  | { state: 'done' | 'current'; stepNumber: number; stepText: string }
  | { state: 'pending'; stepNumber: number };

export function trailRows(
  seen: SeenScaffoldStep[],
  scaffold: ActiveScaffold | null,
): TrailRow[] {
  if (!scaffold) return [];

  const rows: TrailRow[] = seen.map((s) => ({
    state: s.stepNumber === scaffold.stepNumber ? 'current' : 'done',
    stepNumber: s.stepNumber,
    stepText: s.stepText,
  }));

  // The current step may not be in the trail yet on the very first render
  // after a reload, where the panel is restored but the trail is not.
  if (!rows.some((r) => r.state === 'current')) {
    rows.push({
      state: 'current',
      stepNumber: scaffold.stepNumber,
      stepText: scaffold.stepText,
    });
  }

  // A step number the backend never sent stays blank rather than absent: the
  // gap is the point. Guard the total so a bad one cannot spin this.
  const total = Math.min(Math.max(scaffold.totalSteps, rows.length), 24);
  const known = new Set(rows.map((r) => r.stepNumber));
  for (let n = 1; n <= total; n += 1) {
    if (!known.has(n)) rows.push({ state: 'pending', stepNumber: n });
  }

  return rows.sort((a, b) => a.stepNumber - b.stepNumber);
}
