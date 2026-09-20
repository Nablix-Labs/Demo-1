/**
 * Issue #303 — "Phase 1 worked example - currently steps are written one by
 * one, it should be in one page" (Sanya, 14 Sep 2026).
 *
 * Every step used to be drawn at the same coordinates in `replace` mode, so the
 * sheet only ever held the step being spoken. These pin the property that
 * changes: each step gets its own row, and the whole example fits on the page
 * at every length the content authors actually produce.
 */

import { describe, it, expect } from 'vitest';
import {
  workedExampleStepElements, rowY, rowHeight, contentSize, stepLines,
} from '@/lib/workedExampleSheet';
import type { SchemaWorkedExampleStep } from '@/lib/api';

const step = (over: Partial<SchemaWorkedExampleStep> = {}): SchemaWorkedExampleStep => ({
  step_id: 'S1',
  sequence_no: 1,
  screen_content: '3n + 4 = 19',
  narration_text: 'Take four from both sides.',
  ...over,
} as SchemaWorkedExampleStep);

describe('the sheet stacks, rather than overwriting', () => {
  it('writes each step lower than the one before it', () => {
    const ys = [0, 1, 2, 3].map((i) => rowY(i, 4));
    expect(ys).toEqual([...ys].sort((a, b) => a - b));
    expect(new Set(ys).size).toBe(4);
  });

  it('keeps the last step on the page at every authored length', () => {
    // The failure this guards is silent: an overflowing sheet does not throw,
    // it writes step 8 below the bottom edge where nobody ever sees it.
    for (const total of [1, 3, 4, 6, 8, 10, 12]) {
      expect(rowY(total - 1, total)).toBeLessThanOrEqual(0.94);
      expect(rowY(0, total)).toBeGreaterThanOrEqual(0.1);
    }
  });

  it('does not spread a short example across the whole page', () => {
    // Three rows a third of a page apart read as three unrelated statements,
    // not as one piece of working.
    expect(rowHeight(3)).toBeLessThanOrEqual(0.155);
    expect(rowHeight(2)).toEqual(rowHeight(3));
  });

  it('gives a longer example tighter rows, never looser ones', () => {
    expect(rowHeight(12)).toBeLessThan(rowHeight(4));
  });

  it('shrinks the type as the step count grows, so a row holds its line', () => {
    expect(contentSize(4)).toBeGreaterThan(contentSize(8));
    expect(contentSize(8)).toBeGreaterThan(contentSize(12));
  });

  it('keeps the type inside its row at every length', () => {
    // A 22px line in a row 0.06 of a ~700px canvas overlaps the next step.
    // Approximated against the smallest canvas the practice screen renders at.
    const CANVAS_PX = 700;
    for (const total of [1, 3, 4, 6, 8, 10, 12]) {
      expect(contentSize(total)).toBeLessThanOrEqual(rowHeight(total) * CANVAS_PX);
    }
  });
});

describe('what each step actually writes', () => {
  it('numbers the step in the margin and sets the working beside it', () => {
    const [number, content] = workedExampleStepElements(step(), 2, 6);
    expect(number.text).toBe('3');
    expect(content.text).toBe('3n + 4 = 19');
    expect(number.x!).toBeLessThan(content.x!);
    expect(number.y).toBe(content.y);
  });

  it('wraps long working inside its column instead of running off the sheet', () => {
    // Without a wrap width a whole authored sentence runs one line, out of its
    // column and under the side panel, where the panel clips it mid-word.
    const [, content] = workedExampleStepElements(
      step({ screen_content: 'Subtract four from both sides so the term in n stands alone' }),
      0, 6,
    );
    expect(content.wrapWidth).toBeGreaterThan(0);
    expect(content.wrapWidth).toBeLessThanOrEqual(0.85);
  });

  it('writes nothing for a narration-only step', () => {
    // Some authored steps are spoken without being written. A numbered row with
    // nothing in it would be a blank line the student has to account for.
    expect(workedExampleStepElements(step({ screen_content: '' }), 0, 4)).toEqual([]);
    expect(workedExampleStepElements(step({ screen_content: '   ' }), 0, 4)).toEqual([]);
  });

  it('never returns a mark without text, whatever the step carries', () => {
    const marks = workedExampleStepElements(step(), 0, 4);
    for (const mark of marks) expect(mark.text?.trim()).toBeTruthy();
  });
});

/**
 * Manjusha, 19 Sep 2026: `a × a = a² / a × a × a = a³` ran across the sheet as
 * one line. "/ is used to separate the steps, it should be in the second line."
 *
 * The risk the separator creates is division, so these pin both sides of it.
 */
describe('a step authored as two lines in one string', () => {
  it('breaks where the slash separates two complete statements', () => {
    const [, content] = workedExampleStepElements(
      step({ screen_content: 'a × a = a² / a × a × a = a³' }), 0, 4,
    );
    expect(content.text).toBe('a × a = a²\na × a × a = a³');
  });

  it('leaves a division alone — the slash is inside one statement', () => {
    expect(stepLines('6 / 2 = 3')).toBe('6 / 2 = 3');
    expect(stepLines('n = 12 / 4')).toBe('n = 12 / 4');
  });

  it('leaves a slash with no space around it alone', () => {
    expect(stepLines('a/b = c/d')).toBe('a/b = c/d');
  });

  it('breaks a three-part step too', () => {
    expect(stepLines('x = 1 / y = 2 / z = 3')).toBe('x = 1\ny = 2\nz = 3');
  });

  it('leaves an ordinary single step untouched', () => {
    expect(stepLines('3n + 4 = 19')).toBe('3n + 4 = 19');
  });
});

describe('stepLines — cases without an equals sign', () => {
  it('puts each authored case on its own line', () => {
    expect(stepLines('2 + 4 / 7 + 4 / 12 + 4')).toBe('2 + 4\n7 + 4\n12 + 4');
  });
  it('leaves a fraction alone', () => {
    expect(stepLines('x/2 = 3')).toBe('x/2 = 3');
  });
});
