/**
 * Turning a tutor replay into marks on the review board (§8.4).
 *
 * §7.5 is explicit that "the output describes WHAT to write" and "Sanya does
 * not need to generate drawing coordinates", so every position on the board is
 * decided here. The engine sends an ordered list of lines; this module decides
 * where each one lands and what changes on the board when the student moves
 * between steps.
 *
 * The working ACCUMULATES rather than replacing itself. That is the difference
 * between this and the Phase 1 walkthrough, which shows one step at a time on
 * purpose (see WorkedExampleCanvas): there the steps are separate ideas, here
 * they are consecutive lines of one solution, and a student cannot check
 * "t - 3" against the line that produced it if that line has been wiped.
 */

import type { TutorElement } from '@/store/useNumeraStore';
import type { Phase4ReplayStep } from '@/lib/api';

/** Written marks are anchored at their LEFT edge — see the TutorLayer header. */
const LEFT = 0.09;
const TOP = 0.22;
const BOTTOM = 0.86;
/** A hand does not spread three lines over a whole page. */
const LINE_GAP_MAX = 0.15;

const INK = '#1B2A4A';
const SIZE_ROOMY = 38;
const SIZE_TIGHT = 26;

export interface BoardLine {
  x: number;
  y: number;
  size: number;
}

/**
 * Where line `index` of `total` sits on the board, in normalised 0–1 space.
 *
 * The gap is capped rather than simply dividing the space: two steps spread
 * across the full height read as two unrelated statements, not as a solution
 * being worked down the page.
 *
 * The block is then CENTRED in what is left. §8.4 asks for the board to
 * dominate the screen, which makes it tall — and a capped gap starting at a
 * fixed top left a short solution sitting in the upper third with half the
 * board empty beneath it, so the largest element on the page was mostly
 * nothing. Centring uses the height without stretching three lines to fill it.
 */
export function writeLine(index: number, total: number): BoardLine {
  const span = BOTTOM - TOP;
  const gap = total <= 1 ? 0 : Math.min(LINE_GAP_MAX, span / (total - 1));
  const top = TOP + (span - gap * Math.max(total - 1, 0)) / 2;
  return {
    x: LEFT,
    y: top + index * gap,
    // Shrink only once the lines are genuinely close enough to collide.
    size: gap === 0 || gap >= 0.12 ? SIZE_ROOMY : SIZE_TIGHT,
  };
}

function lineElement(
  step: Phase4ReplayStep,
  index: number,
  total: number,
): Omit<TutorElement, 'id'> {
  const { x, y, size } = writeLine(index, total);
  return { kind: 'text', x, y, text: step.tutor_write, size, color: INK };
}

export interface BoardDraw {
  /**
   * `append` adds one line to what is already written; `replace` wipes the
   * board and writes the solution again as far as the current step.
   */
  mode: 'append' | 'replace';
  elements: Array<Omit<TutorElement, 'id'>>;
}

/**
 * What to draw when the player moves from `prevIndex` to `nextIndex`.
 *
 * Playing forward appends the one new line, so the lines already written stay
 * exactly as they were — re-sending them would re-run their reveal animation
 * and the board would appear to rewrite itself on every step.
 *
 * Any other move — stepping back, jumping, restarting — rebuilds the board from
 * the first line. Appending on a backward step would leave the later working
 * standing while the tutor talks about an earlier line, so "previous step"
 * would visibly do nothing; and there is no way to remove a single mark from
 * the tutor layer, by design (it is the non-erasable layer).
 *
 * `prevIndex` of -1 means nothing has been written yet, which makes the first
 * step of a replay a rebuild — the cheap way to guarantee a clean board when a
 * replay opens, whatever the previous one left behind.
 */
export function boardDraw(
  prevIndex: number,
  nextIndex: number,
  steps: Phase4ReplayStep[],
): BoardDraw {
  const total = steps.length;
  if (nextIndex < 0 || nextIndex >= total) return { mode: 'append', elements: [] };

  if (nextIndex === prevIndex + 1 && prevIndex >= 0) {
    return { mode: 'append', elements: [lineElement(steps[nextIndex], nextIndex, total)] };
  }
  return {
    mode: 'replace',
    elements: steps
      .slice(0, nextIndex + 1)
      .map((step, i) => lineElement(step, i, total)),
  };
}
