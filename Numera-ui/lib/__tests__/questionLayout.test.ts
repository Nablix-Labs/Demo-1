import { describe, it, expect } from 'vitest';
import { questionLayout, isBareEquation } from '@/lib/questionText';

describe('stacked cases (Manjusha, 2 Aug)', () => {
  it('splits the three cases into aligned columns', () => {
    // The exact question from §3 of the spec. It used to render as
    // "3 + 5 9 + 5 14 + 5" — one wrapped line, comparison invisible.
    expect(questionLayout('3 + 5\n9 + 5\n14 + 5')).toEqual({
      kind: 'cases',
      rows: [
        ['3', '+', '5'],
        ['9', '+', '5'],
        ['14', '+', '5'],
      ],
    });
  });

  it('does not depend on the sender padding for alignment', () => {
    // Ragged spacing must give the same columns as tidy spacing.
    expect(questionLayout('  3  +  5 \n 9 + 5\n14   +   5')).toEqual(
      questionLayout('3 + 5\n9 + 5\n14 + 5'),
    );
  });

  it('handles Windows line endings', () => {
    expect(questionLayout('3 + 5\r\n9 + 5').kind).toBe('cases');
  });

  it('ignores blank lines between cases', () => {
    expect(questionLayout('3 + 5\n\n9 + 5')).toEqual({
      kind: 'cases',
      rows: [
        ['3', '+', '5'],
        ['9', '+', '5'],
      ],
    });
  });

  it('treats a stack of equations as cases too', () => {
    expect(questionLayout('x + 4 = 9\ny + 4 = 11').kind).toBe('cases');
  });

  it('falls back to prose when the rows do not line up', () => {
    // Inventing a column that is not there would misalign the maths, which is
    // worse than showing it as sent.
    expect(questionLayout('3 + 5\n9 + 5 + 2').kind).toBe('prose');
  });

  it('falls back to prose when any line carries words', () => {
    const q = 'Look at these:\n3 + 5\n9 + 5';
    expect(questionLayout(q)).toEqual({ kind: 'prose', text: q });
  });
});

describe('inline comma-separated cases — what the live backend actually sends', () => {
  // Captured from https://nablix.ai/api on 4 Aug 2026, Q-T01-001.
  const LIVE = '3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number. Write the general rule.';

  it('stacks the cases and keeps the task as the instruction', () => {
    expect(questionLayout(LIVE)).toEqual({
      kind: 'cases',
      rows: [
        ['3', '+', '5'],
        ['9', '+', '5'],
        ['14', '+', '5'],
      ],
      instruction: 'Use n for the changing starting number. Write the general rule.',
    });
  });

  it('handles a run with no trailing instruction', () => {
    expect(questionLayout('3 + 5, 9 + 5, 14 + 5')).toMatchObject({
      kind: 'cases',
      rows: [['3', '+', '5'], ['9', '+', '5'], ['14', '+', '5']],
    });
  });

  it('leaves ordinary prose containing a comma alone', () => {
    const q = 'A box starts with four counters, then receives five more.';
    expect(questionLayout(q)).toEqual({ kind: 'prose', text: q });
  });

  it('does not stack when the parts are not all maths', () => {
    const q = 'Look at 3 + 5, then think about it.';
    expect(questionLayout(q).kind).toBe('prose');
  });

  it('does not stack a single item', () => {
    expect(questionLayout('3 + 5. Write the rule.').kind).toBe('prose');
  });

  it('does not stack ragged rows', () => {
    expect(questionLayout('3 + 5, 9 + 5 + 2. Write the rule.').kind).toBe('prose');
  });

  it('handles a question-mark ending', () => {
    expect(questionLayout('2 + 6, 7 + 6? What is the rule.').kind).toBe('cases');
  });
});

describe('single-line questions are unchanged', () => {
  it('still recognises a bare equation', () => {
    expect(questionLayout('x + 4 = 9')).toEqual({ kind: 'equation', text: 'x + 4 = 9' });
  });

  it('still treats a word problem as prose', () => {
    const q = 'A box starts with four counters and receives 5 more.';
    expect(questionLayout(q)).toEqual({ kind: 'prose', text: q });
  });

  it('treats a question with its own lead-in as prose', () => {
    expect(questionLayout('Solve for x: x + 4 = 9').kind).toBe('prose');
  });

  it('handles an empty question', () => {
    expect(questionLayout('')).toEqual({ kind: 'prose', text: '' });
    expect(questionLayout('   ')).toEqual({ kind: 'prose', text: '' });
  });
});

describe('isBareEquation no longer claims a multi-line stack', () => {
  it('is false for stacked equations', () => {
    // Otherwise the "Solve for x:" lead-in would be glued onto a whole column.
    expect(isBareEquation('x + 4 = 9\ny + 4 = 11')).toBe(false);
  });

  it('is still true for a single equation', () => {
    expect(isBareEquation('x + 4 = 9')).toBe(true);
  });
});
