/**
 * Laying a Phase 1 worked example out as one sheet of working.
 *
 * ── The two requests this has to satisfy at once ───────────────────────────
 *
 * Manjusha, 28 Jul 2026: the example used to render all eight steps at once as
 * a list of cards, "which read as a document to skim rather than a lesson to
 * follow". So each step is now written as its `narration_text` is spoken, and
 * the next one only starts when the voice for this one has finished.
 *
 * Sanya, 14 Sep 2026, issue #303: "Phase 1 worked example - currently steps are
 * written one by one, it should be in one page."
 *
 * Read as layout these contradict each other. Read as what each person was
 * actually looking at, they do not: Manjusha objected to the example arriving
 * ALL AT ONCE as a wall to skim, and Sanya to it never being there as a WHOLE —
 * every step was drawn at the same spot (x 0.08, y 0.34/0.48) in `replace` mode,
 * so writing step 2 rubbed out step 1, and at the end the sheet held one line.
 * A student could not look back at the working, and the walkthrough had nothing
 * to show for itself.
 *
 * What a teacher does at a whiteboard satisfies both: write the steps one at a
 * time, in time with what you are saying, and leave them up. This module is the
 * "leave them up" half — it gives each step its own row down the page, so the
 * pacing is unchanged and the finished sheet is the whole worked example.
 *
 * Geometry lives here rather than in the screen because none of it is testable
 * through JSX (the runner has no JSX transform) and all of it is arithmetic
 * that goes wrong quietly: a sheet that overflows does not throw, it just puts
 * step 8 off the bottom edge where nobody sees it.
 */

import type { SchemaWorkedExampleStep } from '@/lib/api';
import type { TutorElement } from '@/store/useNumeraStore';
import { inkFor } from '@/lib/inkRoles';

/** First row's baseline. Clear of the heading that sits above the canvas. */
const TOP = 0.12;
/** Nothing may be written below this — the toolbar and mic live under it. */
const BOTTOM = 0.94;
/**
 * Tallest a row may be, however few steps there are.
 *
 * Without a cap, a three-step example spreads its rows a third of a page apart
 * and reads as three unrelated statements rather than one piece of working.
 */
const MAX_ROW = 0.155;
/** Left edge of the step number, and of the working beside it. */
const NUMBER_X = 0.055;
const CONTENT_X = 0.105;
/** Working wraps inside its column instead of running under the side panel. */
const CONTENT_WRAP = 0.8;

const NUMBER_COLOR = '#5A6478';
const CONTENT_COLOR = '#1B2A4A';

/**
 * Type size for the working, chosen from how many rows have to fit.
 *
 * A worked example is authored anywhere from three steps to a dozen, and one
 * fixed size cannot serve both: 34px is right for four steps and overruns its
 * row at ten. Stepped rather than continuous so that two examples of similar
 * length look like the same lesson.
 */
export function contentSize(total: number): number {
  if (total <= 4) return 30;
  if (total <= 6) return 26;
  if (total <= 8) return 22;
  return 19;
}

/** Vertical distance between one step's baseline and the next. */
export function rowHeight(total: number): number {
  if (total <= 1) return MAX_ROW;
  return Math.min(MAX_ROW, (BOTTOM - TOP) / total);
}

/** Where step `index` is written, as a fraction of canvas height. */
export function rowY(index: number, total: number): number {
  return TOP + rowHeight(total) * index;
}

/**
 * Break a step that was authored as two lines of working in one string.
 *
 * Manjusha, 19 Sep 2026: `a × a = a² / a × a × a = a³` arrived as one step and
 * ran across the sheet as a single line — "/ is used to separate the steps, it
 * should be in the second line".
 *
 * The catch is that `/` is also division, and this is a maths tutor: splitting
 * on every slash would turn the step `6 / 2 = 3` into two lines reading "6" and
 * "2 = 3". So the slash is only read as a separator when it divides two
 * COMPLETE statements — every part has an `=` of its own. A division has its
 * slash inside one side of the equation, so it never qualifies.
 *
 * Authoring a real newline, or two separate steps, is still the better fix and
 * is unaffected by this — Konva already renders `\n`.
 */
export function stepLines(content: string): string {
  // ' | ' is the same separator in newer content ('a × a = a² | a × a × a = a³').
  const parts = content.split(/ [/|] /).map((part) => part.trim());
  if (parts.length < 2) return content;
  // A spaced " / " between non-empty parts is the authored case separator
  // ("2 + 4 / 7 + 4 / 12 + 4"); a fraction is written without spaces (a/b).
  // It used to require an '=' in every part, which left the three-case
  // opening of a worked example on one line with slashes (#303, 21 Sep).
  if (parts.some((part) => !part)) return content;
  // Mixed parts — one statement with a spaced division in it ('6 / 2 = 3')
  // — stay as written. All-equations or all-expressions are separate cases.
  const withEquals = parts.filter((part) => part.includes('=')).length;
  if (withEquals !== 0 && withEquals !== parts.length) return content;
  return parts.join('\n');
}

/**
 * Where each step goes when steps can be more than one line tall.
 *
 * `rowY` spaces steps evenly, which is right while every step is one line. A
 * step authored as two cases ('a × a = a² | a × a × a = a³') is two lines tall,
 * and its second line ran into the next step (dev-screens/orientation-board,
 * 4 Oct). So the sheet is laid out in LINES: each step takes as many rows as it
 * has lines, and the type size is chosen from the total line count.
 */
export interface SheetLayout {
  /** Baseline of each step, as a fraction of canvas height. */
  y: number[];
  /** Left edge of each step's number; its working starts a fixed gap right of it. */
  x: number[];
  size: number;
  wrap: number;
  lines: number;
  columns: 1 | 2;
}

/**
 * Past this many lines a single column turns into small writing down the left
 * third of an empty board (ALG-ORI-02: nine lines at 19px, 4 Oct). Two columns
 * use the width and let each line be written larger.
 */
const ONE_COLUMN_MAX_LINES = 5;
const COLUMN_2_X = 0.52;
const COLUMN_WRAP = 0.4;

export function sheetLayout(steps: SchemaWorkedExampleStep[]): SheetLayout {
  const heights = steps.map((step) => {
    const content = step.screen_content?.trim();
    return content ? stepLines(content).split('\n').length : 0;
  });
  const lines = Math.max(1, heights.reduce((a, b) => a + b, 0));

  if (lines <= ONE_COLUMN_MAX_LINES) {
    const unit = rowHeight(lines);
    const y: number[] = [];
    let used = 0;
    for (const h of heights) { y.push(TOP + unit * used); used += h; }
    return { y, x: heights.map(() => NUMBER_X), size: contentSize(lines), wrap: CONTENT_WRAP, lines, columns: 1 };
  }

  // Split at the step boundary closest to half the lines, so the columns are
  // as even as they can be without breaking a step across them.
  let split = 1;
  let best = Infinity;
  let running = 0;
  for (let i = 0; i < heights.length - 1; i++) {
    running += heights[i];
    const diff = Math.abs(lines / 2 - running);
    if (diff < best) { best = diff; split = i + 1; }
  }
  const leftLines = heights.slice(0, split).reduce((a, b) => a + b, 0);
  const tallest = Math.max(leftLines, lines - leftLines);
  const unit = rowHeight(tallest);
  // Sized from the longest LINE that has to fit a column, not the longest
  // step: a two-case step is long as a string but short once split.
  const longest = Math.max(...steps.map((st) =>
    Math.max(...stepLines(st.screen_content?.trim() ?? '').split('\n').map((l) => l.length))));
  const size = longest <= 24 ? 32 : longest <= 30 ? 28 : 24;

  const y: number[] = [];
  const x: number[] = [];
  let used = 0;
  heights.forEach((h, i) => {
    if (i === split) used = 0;
    y.push(TOP + unit * used);
    x.push(i < split ? NUMBER_X : COLUMN_2_X);
    used += h;
  });
  return { y, x, size, wrap: COLUMN_WRAP, lines, columns: 2 };
}

/**
 * One step's marks: its number, and the working beside it.
 *
 * Returns nothing for a step with no `screen_content`. Some authored steps are
 * narration only — the tutor says something without writing it — and inventing
 * a mark for one would put an empty numbered row on the sheet.
 */
export function workedExampleStepElements(
  step: SchemaWorkedExampleStep,
  index: number,
  total: number,
  layout?: Pick<SheetLayout, 'y' | 'size'> & Partial<Pick<SheetLayout, 'x' | 'wrap'>>,
): Array<Omit<TutorElement, 'id'>> {
  const content = step.screen_content?.trim();
  if (!content) return [];
  const y = layout?.y[index] ?? rowY(index, total);
  const size = layout?.size ?? contentSize(total);
  const numberX = layout?.x?.[index] ?? NUMBER_X;
  const contentX = numberX + (CONTENT_X - NUMBER_X);
  return [
    {
      kind: 'text',
      x: numberX,
      y,
      text: `${index + 1}`,
      // Small enough to read as a margin number rather than as working.
      size: Math.round(size * 0.62),
      color: NUMBER_COLOR,
    },
    {
      kind: 'text',
      x: contentX,
      y,
      text: stepLines(content),
      size,
      color: step.emphasis ? inkFor(step.emphasis) : CONTENT_COLOR,
      wrapWidth: layout?.wrap ?? CONTENT_WRAP,
    },
  ];
}
