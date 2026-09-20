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
  const parts = content.split(' / ').map((part) => part.trim());
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
): Array<Omit<TutorElement, 'id'>> {
  const content = step.screen_content?.trim();
  if (!content) return [];
  const y = rowY(index, total);
  const size = contentSize(total);
  return [
    {
      kind: 'text',
      x: NUMBER_X,
      y,
      text: `${index + 1}`,
      // Small enough to read as a margin number rather than as working.
      size: Math.round(size * 0.62),
      color: NUMBER_COLOR,
    },
    {
      kind: 'text',
      x: CONTENT_X,
      y,
      text: stepLines(content),
      size,
      color: CONTENT_COLOR,
      wrapWidth: CONTENT_WRAP,
    },
  ];
}
