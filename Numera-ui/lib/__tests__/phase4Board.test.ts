/**
 * Writing the tutor's solution onto the review board.
 *
 * The rule worth protecting is that playing forward must not re-send lines that
 * are already written: the reveal store animates any element it has not seen,
 * so a step that re-sends the whole solution makes the board rewrite itself
 * from the top every time the tutor moves on.
 */

import { describe, expect, it } from 'vitest';
import { writeLine, boardDraw } from '@/lib/phase4Board';
import type { Phase4ReplayStep } from '@/lib/api';

const steps = (n: number): Phase4ReplayStep[] =>
  Array.from({ length: n }, (_, i) => ({
    sequence_no: i + 1,
    narration: `Narration ${i + 1}`,
    tutor_write: `Line ${i + 1}`,
  }));

describe('where a line lands', () => {
  it('writes down the page in order', () => {
    const ys = [0, 1, 2, 3].map((i) => writeLine(i, 4).y);
    expect(ys).toEqual([...ys].sort((a, b) => a - b));
    expect(new Set(ys).size).toBe(4);
  });

  it('keeps every line on the board', () => {
    for (const total of [1, 2, 5, 9, 14]) {
      for (let i = 0; i < total; i++) {
        const { x, y } = writeLine(i, total);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(y).toBeLessThanOrEqual(1);
        expect(x).toBeGreaterThan(0);
        expect(x).toBeLessThan(1);
      }
    }
  });

  it('does not spread two lines across the whole page', () => {
    // A capped gap is what makes consecutive lines read as one solution rather
    // than as two unrelated statements at opposite ends of the board.
    // Compared with a tolerance: the gap IS the cap here, and subtracting two
    // normalised positions lands a float hair above it.
    const gap = writeLine(1, 2).y - writeLine(0, 2).y;
    expect(gap).toBeLessThanOrEqual(0.15 + 1e-9);
  });

  it('shrinks the writing only once the lines would collide', () => {
    expect(writeLine(0, 3).size).toBe(writeLine(0, 1).size);
    expect(writeLine(0, 12).size).toBeLessThan(writeLine(0, 3).size);
  });
});

describe('playing forward', () => {
  it('appends only the new line', () => {
    // Re-sending line 1 here would restart its reveal — the board would appear
    // to rewrite itself on every step.
    const draw = boardDraw(0, 1, steps(3));
    expect(draw.mode).toBe('append');
    expect(draw.elements).toHaveLength(1);
    expect(draw.elements[0].text).toBe('Line 2');
  });

  it('rebuilds the board on the first step of a replay', () => {
    // prevIndex -1 means nothing is written yet. A rebuild guarantees a clean
    // board whatever the previous replay left behind.
    const draw = boardDraw(-1, 0, steps(3));
    expect(draw.mode).toBe('replace');
    expect(draw.elements.map((e) => e.text)).toEqual(['Line 1']);
  });
});

describe('moving anywhere other than forward one step', () => {
  it('rewrites the solution as far as the step stepped back to', () => {
    // Appending on a backward step would leave the later working standing while
    // the tutor talks about an earlier line — "previous step" would look dead.
    const draw = boardDraw(2, 1, steps(3));
    expect(draw.mode).toBe('replace');
    expect(draw.elements.map((e) => e.text)).toEqual(['Line 1', 'Line 2']);
  });

  it('rewrites from the top on a restart', () => {
    const draw = boardDraw(2, 0, steps(3));
    expect(draw.mode).toBe('replace');
    expect(draw.elements.map((e) => e.text)).toEqual(['Line 1']);
  });

  it('rewrites when the student jumps several steps ahead', () => {
    const draw = boardDraw(0, 2, steps(3));
    expect(draw.mode).toBe('replace');
    expect(draw.elements.map((e) => e.text)).toEqual(['Line 1', 'Line 2', 'Line 3']);
  });

  it('redraws the same step rather than doubling it', () => {
    const draw = boardDraw(1, 1, steps(3));
    expect(draw.mode).toBe('replace');
    expect(draw.elements.map((e) => e.text)).toEqual(['Line 1', 'Line 2']);
  });
});

describe('an index off the end of the replay', () => {
  it('draws nothing rather than throwing', () => {
    // The player reports index === steps.length when it finishes; the board
    // should simply stop, leaving the completed solution standing.
    expect(boardDraw(2, 3, steps(3)).elements).toEqual([]);
    expect(boardDraw(0, -1, steps(3)).elements).toEqual([]);
  });
});

describe('what is written', () => {
  it('writes tutor_write and never the narration', () => {
    // §7.5: narration is spoken, tutor_write is written. Writing the narration
    // turns the board into subtitles.
    const draw = boardDraw(-1, 0, steps(2));
    expect(draw.elements[0].text).toBe('Line 1');
    expect(JSON.stringify(draw.elements)).not.toContain('Narration');
  });
});

describe('using the height of a board built to dominate the screen', () => {
  it('centres a short solution instead of stranding it at the top', () => {
    // Three lines on a tall board used to sit in the upper third with half the
    // board empty beneath them — the largest element on the page, mostly nothing.
    const ys = [0, 1, 2].map((i) => writeLine(i, 3).y);
    const above = ys[0];
    const below = 1 - ys[2];
    expect(Math.abs(above - below)).toBeLessThan(0.12);
  });

  it('still starts near the top when the lines fill the board', () => {
    // A long solution has no slack to centre, so it must not creep downward and
    // push its last line off the bottom.
    const last = writeLine(11, 12).y;
    expect(last).toBeLessThanOrEqual(0.9);
    expect(writeLine(0, 12).y).toBeLessThanOrEqual(0.3);
  });
});
