/**
 * Learning-flow phases — the gated funnel a student moves through.
 *
 *   diagnostic → orientation → workbook → practice → review
 *
 * Each screen declares the phase it belongs to; PhaseGate blocks a screen until
 * its prerequisite phase is complete. Completion is tracked in the store
 * (`phasesDone`, persisted) and the gate offers a "Skip — testing only" bypass.
 * In production these unlocks would be backend-driven; the shape stays the same.
 */

export type LearningPhase =
  | 'diagnostic'
  | 'orientation'
  | 'teach'
  | 'workbook'
  | 'practice'
  | 'review';

/** Canonical order of the funnel. */
export const PHASE_ORDER: LearningPhase[] = [
  'diagnostic', 'orientation', 'teach', 'workbook', 'practice', 'review',
];

/** The single phase that must be complete before a phase unlocks (null = entry). */
export const PHASE_PREREQ: Record<LearningPhase, LearningPhase | null> = {
  diagnostic: null,
  orientation: 'diagnostic',
  teach: 'orientation',
  workbook: 'diagnostic',
  practice: 'orientation',
  review: 'practice',
};

/** Where to send a student to complete a phase, plus copy for the gate screen. */
export const PHASE_META: Record<
  LearningPhase,
  { label: string; href: string; cta: string; blurb: string }
> = {
  diagnostic: {
    label: 'Diagnostic',
    href: '/diagnostic',
    cta: 'Take the diagnostic',
    blurb: 'A one-time placement check so Numera knows your level.',
  },
  orientation: {
    label: 'Orientation',
    href: '/orientation/algebra',
    cta: 'Watch the orientation',
    blurb: 'A short concept video before you start practising.',
  },
  teach: {
    label: 'Teacher Mode',
    href: '/teach/algebra',
    cta: 'Teach it back',
    blurb: 'Explain the idea back to Numera in your own words.',
  },
  workbook: {
    label: 'Workbook',
    href: '/workbook',
    cta: 'Open your workbook',
    blurb: 'Your topics, matched to your school year.',
  },
  practice: {
    label: 'Practice',
    href: '/practice',
    cta: 'Begin practice',
    blurb: 'Solve on your own — the tutor watches quietly.',
  },
  review: {
    label: 'Review',
    href: '/review',
    cta: 'Go to review',
    blurb: 'The tutor marks your work and talks it through.',
  },
};

/**
 * Prerequisite phases still outstanding before `phase` can be entered, in the
 * order they should be done. Empty list ⇒ the phase is unlocked.
 */
export function missingPrereqs(
  phase: LearningPhase,
  done: LearningPhase[],
): LearningPhase[] {
  const chain: LearningPhase[] = [];
  let p = PHASE_PREREQ[phase];
  while (p) {
    chain.unshift(p);
    p = PHASE_PREREQ[p];
  }
  return chain.filter((x) => !done.includes(x));
}
