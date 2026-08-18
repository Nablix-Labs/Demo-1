/**
 * Pointing at part of the question.
 *
 * Nearly every test here is about the same failure: highlighting the wrong
 * character. The backend sends an exact span precisely because the token text
 * is ambiguous — "n" and "4" occur repeatedly in an ordinary word problem — so
 * a renderer that searches instead of slicing teaches the student about the
 * wrong symbol, and does it silently.
 */

import { describe, expect, it, vi, afterEach } from 'vitest';
import { usableAnchors, anchorSegments, locateFragment, fragmentRanges } from '@/lib/questionAnchors';
import type { QuestionAnchor } from '@/lib/questionAnchors';

// Chiru's own example. Note "n" also appears inside "and", "points", "then",
// "new-score" — searching for it finds "n" at index 4, not the variable.
const Q = 'Ravi scores n points and then scores 4 more. Write the new-score rule.';

const anchor = (over: Partial<QuestionAnchor> = {}): QuestionAnchor => ({
  token_id: 'Q-T01-003:QTOKEN:3',
  text: 'n',
  char_start: 12,
  char_end: 13,
  label: 'changes',
  ...over,
});

afterEach(() => vi.restoreAllMocks());

describe('the span the backend sent', () => {
  it('slices to the token text', () => {
    // Guards the fixture itself: if this drifts, every test below is testing
    // the wrong string.
    expect(Q.slice(12, 13)).toBe('n');
  });

  it('lands on the variable where a search would not', () => {
    // The hazard, made concrete. Here the first "n" is inside "Nina" and the
    // first "4" is the wrong one of two, so indexOf highlights a letter in the
    // student's name and the wrong number — silently, and confidently.
    const NINA = 'Nina scores n points, then scores 4 more after 4 rounds.';
    expect(NINA.indexOf('n')).toBe(2);
    expect(NINA.slice(12, 13)).toBe('n');

    const [, variable, , four] = anchorSegments(NINA, [
      anchor({ token_id: 'A', text: 'n', char_start: 12, char_end: 13 }),
      anchor({ token_id: 'B', text: '4', char_start: 47, char_end: 48, label: 'stays fixed' }),
    ]);
    expect(variable).toMatchObject({ text: 'n' });
    expect(variable.anchor?.token_id).toBe('A');
    // The SECOND 4, which is the one the backend pointed at.
    expect(four.anchor?.token_id).toBe('B');
    expect(NINA.indexOf('4')).toBe(34);
  });

  it('highlights the variable, not the first matching letter', () => {
    const [before, anchored] = anchorSegments(Q, [anchor()]);
    expect(before.text).toBe('Ravi scores ');
    expect(anchored.anchor?.label).toBe('changes');
    expect(anchored.text).toBe('n');
  });

  it('keeps the whole question across the segments', () => {
    const segments = anchorSegments(Q, [anchor(), anchor({
      token_id: 'T4', text: '4', char_start: 37, char_end: 38, label: 'stays fixed',
    })]);
    expect(segments.map((s) => s.text).join('')).toBe(Q);
    expect(segments.filter((s) => s.anchor).map((s) => s.text)).toEqual(['n', '4']);
  });
});

describe('anchors that cannot be trusted', () => {
  it('drops a span that does not slice back to its own text', () => {
    // The contract breach Chiru asked to be told about: it means the string we
    // rendered is not current_question.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(usableAnchors(Q, [anchor({ char_start: 4, char_end: 5 })])).toEqual([]);
    expect(warn).toHaveBeenCalled();
  });

  it('reports the mismatch rather than throwing', () => {
    // A wrong highlight is a teaching error; refusing to render the question
    // over one bad span would turn it into a blocked lesson.
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const segments = anchorSegments(Q, [anchor({ char_start: 4, char_end: 5 })]);
    expect(segments.map((s) => s.text).join('')).toBe(Q);
  });

  it('drops a span that runs off the end of the question', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(usableAnchors(Q, [anchor({ char_start: 900, char_end: 901 })])).toEqual([]);
    expect(usableAnchors(Q, [anchor({ char_start: 60, char_end: 999 })])).toEqual([]);
  });

  it('drops an empty or inverted span', () => {
    expect(usableAnchors(Q, [anchor({ char_start: 12, char_end: 12 })])).toEqual([]);
    expect(usableAnchors(Q, [anchor({ char_start: 13, char_end: 12 })])).toEqual([]);
  });

  it('drops a non-integer span rather than slicing on a fraction', () => {
    expect(usableAnchors(Q, [anchor({ char_start: 12.5, char_end: 13 })])).toEqual([]);
  });
});

describe('de-duplication', () => {
  it('keys on token_id, which is stable for a question', () => {
    // The two spans are far apart and do not overlap, so ONLY the token_id
    // rule can drop the second — an identical pair would be caught by the
    // overlap rule instead and prove nothing about de-duplication.
    const kept = usableAnchors(Q, [
      anchor({ token_id: 'SAME', text: 'n', char_start: 12, char_end: 13 }),
      anchor({ token_id: 'SAME', text: '4', char_start: 37, char_end: 38 }),
    ]);
    expect(kept).toHaveLength(1);
    expect(kept[0].char_start).toBe(12);
  });

  it('drops an anchor overlapping one already kept', () => {
    // Two spans over the same characters cannot both be rendered as a flat run,
    // and nesting them would highlight the same character twice.
    const kept = usableAnchors(Q, [
      anchor({ token_id: 'A', text: 'n points', char_start: 12, char_end: 20 }),
      anchor({ token_id: 'B', text: 'points', char_start: 14, char_end: 20 }),
    ]);
    expect(kept.map((a) => a.token_id)).toEqual(['A']);
  });

  it('orders anchors by position, whatever order they arrived in', () => {
    const kept = usableAnchors(Q, [
      anchor({ token_id: 'T4', text: '4', char_start: 37, char_end: 38 }),
      anchor(),
    ]);
    expect(kept.map((a) => a.char_start)).toEqual([12, 37]);
  });
});

describe('an empty anchor list', () => {
  it('is normal and renders the question unchanged', () => {
    // "Empty array is normal and means nothing to point at this turn."
    for (const empty of [[], null, undefined]) {
      const segments = anchorSegments(Q, empty);
      expect(segments).toHaveLength(1);
      expect(segments[0]).toEqual({ text: Q, anchor: null });
    }
  });
});

describe('rendering only part of the question', () => {
  // The layout splits a question into fragments — a grid of cases plus the
  // instruction after it — so each fragment renders its own span range.
  it('excludes an anchor belonging to a different fragment', () => {
    const segments = anchorSegments(Q, [anchor()], 44, Q.length);
    expect(segments.every((s) => s.anchor === null)).toBe(true);
    expect(segments.map((s) => s.text).join('')).toBe(Q.slice(44));
  });

  it('includes an anchor inside the fragment', () => {
    const segments = anchorSegments(Q, [anchor()], 0, 20);
    expect(segments.filter((s) => s.anchor)).toHaveLength(1);
    expect(segments.map((s) => s.text).join('')).toBe(Q.slice(0, 20));
  });

  it('drops an anchor straddling the fragment boundary', () => {
    // Rendering half a highlighted token would point at half a symbol.
    const straddling = anchor({ token_id: 'S', text: 'n points', char_start: 12, char_end: 20 });
    expect(anchorSegments(Q, [straddling], 0, 16).every((s) => s.anchor === null)).toBe(true);
  });
});

describe('locating a rendered fragment', () => {
  const CASES = '3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.';

  it('resolves REPEATED fragments in order through a moving cursor', () => {
    // "+ 5" is the same text three times over. Without the cursor every one
    // resolves to the first occurrence and all three cases would claim the
    // same offsets — which is exactly how a fragment ends up carrying another
    // fragment's anchors.
    let cursor = 0;
    const found: number[] = [];
    for (const frag of ['+ 5', '+ 5', '+ 5']) {
      const at = locateFragment(CASES, frag, cursor);
      found.push(at);
      cursor = at + frag.length;
    }
    expect(found).toEqual([2, 9, 17]);
    expect(new Set(found).size).toBe(3);
  });

  it('returns -1 for text the layout added rather than sliced', () => {
    // The "Solve for x:" lead-in is not part of the question.
    expect(locateFragment(CASES, 'Solve for x:', 0)).toBe(-1);
    expect(locateFragment(CASES, '', 0)).toBe(-1);
  });
});

describe('resolving the fragments the layout renders', () => {
  // A comma-separated run of cases is split into a grid, so the question
  // reaches the screen as several fragments rather than one string.
  const CASES = '3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.';

  it('gives each repeated fragment its own occurrence', () => {
    const ranges = fragmentRanges(CASES, ['3', '+', '5', '9', '+', '5', '14', '+', '5']);
    const plus = ranges.filter((_, i) => i % 3 === 1).map((r) => r.from);
    expect(new Set(plus).size).toBe(3);
    // Every fragment slices back to itself.
    const frags = ['3', '+', '5', '9', '+', '5', '14', '+', '5'];
    ranges.forEach((r, i) => {
      expect(CASES.slice(r.from as number, r.to as number)).toBe(frags[i]);
    });
  });

  it('resolves the instruction after the cases, not before them', () => {
    const [, instruction] = fragmentRanges(CASES, ['3 + 5', 'Use n for the changing starting number.']);
    expect(CASES.slice(instruction.from as number, instruction.to as number))
      .toBe('Use n for the changing starting number.');
  });

  it('returns null for text the layout added rather than sliced', () => {
    // The "Solve for x:" lead-in is not part of the question and carries no
    // anchors — the backend never measured it.
    const [leadIn, equation] = fragmentRanges('x + 4 = 9', ['Solve for x:', 'x + 4 = 9']);
    expect(leadIn).toEqual({ from: null, to: null });
    expect(equation).toEqual({ from: 0, to: 9 });
  });
});
