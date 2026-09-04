/**
 * The stage strip under the review board.
 *
 * The design shows five named stages — Spot the pattern, Find the error, Build
 * the rule, Try an example, Takeaway — with a tick on the ones already passed
 * and the current one lit.
 *
 * The names are the backend's to author (`replay_steps[].stage_label`), and
 * until it does the honest thing to show is the steps this replay actually has.
 * Hardcoding five names would be the client asserting a shape it cannot see: a
 * replay with three steps would render two stages the student never reaches,
 * and one with seven would show them stuck on "Takeaway" for three steps
 * running. Both tell the student they are somewhere they are not, which is the
 * one thing a progress indicator must never do.
 *
 * So: labelled stages when the backend labels them, numbered steps when it does
 * not, and the strip is the same component either way.
 */

export interface Stage {
  /** What the strip prints. */
  label: string;
  /** The step index this stage begins at. */
  startIndex: number;
  /** True once the player has moved past this stage. */
  done: boolean;
  /** True while the player is inside it. */
  current: boolean;
}

interface StepLike {
  stage_label?: string | null;
}

/**
 * Collapse steps into stages.
 *
 * Consecutive steps sharing a label are ONE stage — a stage is a phase of the
 * explanation, not a step, and "Find the error" spread over three steps is
 * still one thing the student is doing. Order comes from the steps themselves;
 * a label that reappears later after a different one in between starts a new
 * stage rather than reopening the old one, because going back to a stage the
 * student has already passed would move the tick backwards.
 */
export function stagesFrom(steps: readonly StepLike[], activeIndex: number): Stage[] {
  const labelled = steps.some((s) => s.stage_label?.trim());

  const groups: Array<{ label: string; startIndex: number; endIndex: number }> = [];
  steps.forEach((step, i) => {
    const label = labelled ? step.stage_label?.trim() || '' : `Step ${i + 1}`;
    const last = groups[groups.length - 1];
    // Only a non-empty label may extend the previous group. An unlabelled step
    // in a labelled replay belongs to nothing, and folding it into whatever
    // came before would silently lengthen that stage.
    if (last && label !== '' && last.label === label) {
      last.endIndex = i;
      return;
    }
    groups.push({ label, startIndex: i, endIndex: i });
  });

  return groups
    .filter((g) => g.label !== '')
    .map((g) => ({
      label: g.label,
      startIndex: g.startIndex,
      done: activeIndex > g.endIndex,
      current: activeIndex >= g.startIndex && activeIndex <= g.endIndex,
    }));
}

/**
 * Total runtime, in milliseconds, or null when the backend timed nothing.
 *
 * Null is the load-bearing case. The design's transport bar shows "01:48 /
 * 04:32" with a scrubber, and both are meaningless without real durations —
 * so the caller renders neither rather than counting a made-up clock, which
 * would run out while the tutor was still talking.
 *
 * A PARTIALLY timed replay is treated as untimed. Summing the steps that
 * happen to carry a duration produces a total shorter than the replay, and a
 * progress bar that reaches the end early is worse than none at all.
 */
export function totalDurationMs(
  steps: readonly { duration_ms?: number | null }[],
): number | null {
  if (steps.length === 0) return null;
  let total = 0;
  for (const step of steps) {
    const ms = step.duration_ms;
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return null;
    total += ms;
  }
  return total;
}

/** Milliseconds elapsed at the START of a step — where the scrubber sits. */
export function elapsedMsAt(
  steps: readonly { duration_ms?: number | null }[],
  index: number,
): number {
  let elapsed = 0;
  for (let i = 0; i < index && i < steps.length; i += 1) {
    elapsed += steps[i].duration_ms ?? 0;
  }
  return elapsed;
}

/** "04:32". Seconds floor rather than round, so a clock never shows its end early. */
export function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}
