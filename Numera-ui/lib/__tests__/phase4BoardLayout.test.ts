/**
 * Board layout (PR #257).
 *
 * The failure worth guarding is silent: a brace whose labels drift out of line
 * with the values above them still looks deliberate, so "+4 +4 +4" ends up
 * under the wrong numbers and the student reads a claim the tutor never made.
 */

import { describe, it, expect } from 'vitest';
import { braceFit, columnsAbove, usesBoards } from '@/lib/phase4BoardLayout';
import type { Phase4BoardElement } from '@/lib/api';

const row = (n: number): Phase4BoardElement =>
  ({ kind: 'value_row', values: Array.from({ length: n }, (_, i) => String(i)), arrow_label: 'changes' });
const brace = (...labels: string[]): Phase4BoardElement =>
  ({ kind: 'brace', over: 'value_row', labels });

describe('where a brace puts its labels', () => {
  it('aligns one label per column', () => {
    // The design's "+ 4  + 4  + 4" under 2, 5, 8.
    expect(braceFit(['+ 4', '+ 4', '+ 4'], 3))
      .toEqual({ mode: 'columns', labels: ['+ 4', '+ 4', '+ 4'], columns: 3 });
  });

  it('spans a single caption', () => {
    expect(braceFit(['stays the same'], 3)).toEqual({ mode: 'span', label: 'stays the same' });
  });

  it('spans rather than half-aligning when the counts disagree', () => {
    // Three labels under four values would sit each one under the wrong number
    // while looking intentional. A partial alignment is worse than none.
    expect(braceFit(['+ 4', '+ 4', '+ 4'], 4).mode).toBe('span');
  });

  it('keeps every authored label when it has to span', () => {
    // They were authored and the student should see them; joining makes it
    // visibly one caption rather than dropping two of the three.
    expect(braceFit(['a', 'b'], 5)).toEqual({ mode: 'span', label: 'a  b' });
  });

  it('spans when there is nothing above to measure against', () => {
    expect(braceFit(['+ 4', '+ 4'], 0).mode).toBe('span');
  });

  it('ignores blank labels rather than aligning to them', () => {
    // Two real labels and a blank must not count as three columns — that would
    // align the two under the wrong values and leave a gap under the third.
    expect(braceFit(['+ 4', '  ', '+ 4'], 3)).toEqual({ mode: 'span', label: '+ 4  + 4' });
    expect(braceFit([' ', ''], 2)).toEqual({ mode: 'span', label: '' });
  });
});

describe('what a brace sits over', () => {
  it('takes its columns from the value row above it', () => {
    expect(columnsAbove([row(3), brace('+ 4', '+ 4', '+ 4')], 1)).toBe(3);
  });

  it('reaches through a brace to the row that brace was under', () => {
    // The design stacks them: "+4 +4 +4" over the values, then "stays the same"
    // under that. Both belong to the same three columns.
    expect(columnsAbove([row(3), brace('+ 4', '+ 4', '+ 4'), brace('stays the same')], 2)).toBe(3);
  });

  it('has nothing to align to when something else intervenes', () => {
    // Once another element is between them the brace is no longer under the
    // row, so aligning to it would be aligning to something that has moved.
    expect(columnsAbove([row(3), { kind: 'expression', text: 'n + 4' }, brace('a', 'b', 'c')], 2)).toBe(0);
  });

  it('has nothing to align to when the brace comes first', () => {
    expect(columnsAbove([brace('a')], 0)).toBe(0);
  });
});

describe('choosing the surface', () => {
  it('uses boards when any step has one', () => {
    expect(usesBoards([{}, { board: { elements: [row(2)] } }])).toBe(true);
  });

  it('keeps the handwriting canvas when no step has a board', () => {
    // The fallback PR #257 asks us to preserve exactly: absent `board` must
    // leave the previous rendering untouched.
    expect(usesBoards([{}, { board: null }])).toBe(false);
  });

  it('keeps the canvas for a board that arrived empty', () => {
    // An empty element list draws nothing, so switching surfaces for it would
    // replace a working explanation with a blank panel.
    expect(usesBoards([{ board: { elements: [] } }])).toBe(false);
  });
});
