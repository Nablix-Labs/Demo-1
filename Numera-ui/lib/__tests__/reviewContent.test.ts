/**
 * The Review screen must never show demo work as a student's own.
 *
 * Row 42 was "Review & feedback / Linear equations · today" printed over a
 * session about "What Is Algebra?". The fix keyed on `outcomes.length > 0`,
 * which fixed the reported case and left the one underneath it: a live session
 * that ends having graded nothing still fell through to the demo — the demo
 * label, the demo worksheets and the demo summary, presented as real results.
 *
 * Row 17 makes that state ordinary rather than exotic: a session with zero
 * per_question_history ends successfully and grades nothing.
 */

import { describe, it, expect } from 'vitest';
import { reviewSource } from '@/lib/reviewContent';

describe('what the Review screen may show', () => {
  it('shows the backend’s own results when there are some', () => {
    expect(reviewSource(true, 3)).toBe('backend');
  });

  it('says nothing was graded rather than inventing it (rows 17 and 42)', () => {
    expect(reviewSource(true, 0)).toBe('none');
  });

  it('still shows the demo when there is no backend — that is the demo’s job', () => {
    expect(reviewSource(false, 0)).toBe('demo');
  });

  it('never reaches for the demo once a backend is configured', () => {
    for (const graded of [0, 1, 7]) {
      expect(reviewSource(true, graded)).not.toBe('demo');
    }
  });
});
