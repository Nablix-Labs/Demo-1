/**
 * What the review screen may say when it has no outcomes.
 *
 * An empty outcome list is what arrives when the backend has not put the
 * summary together. It is NOT evidence about the student. The screen used to
 * explain the gap anyway — "This session ended before any questions were
 * completed" — and showed that to Manjusha (20 Sep) the moment she finished a
 * whole topic: "successfully reached phase 4, but something wrong here".
 *
 * The claim was never checkable: `endFailed` was declared and never assigned,
 * so that sentence was the only thing this state could ever render, and it
 * fired purely on `outcomes.length === 0`.
 *
 * Testing the copy rather than the component because the copy is the defect.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const source = readFileSync(join(process.cwd(), 'app/review/page.tsx'), 'utf8');

describe('the empty-review state', () => {
  it('never tells the student they completed no questions', () => {
    // The frontend cannot know this. Only the backend can say it.
    expect(source).not.toMatch(/ended before any questions were completed/);
    expect(source).not.toMatch(/Nothing to review yet/);
  });

  it('says what is actually known — the results are not here', () => {
    expect(source).toMatch(/Results not ready/);
    expect(source).toMatch(/could not load your results/);
  });

  it('offers a retry, because an empty list is usually a missing review', () => {
    // Previously the only way out was "Back to the lesson", which throws away
    // a review that was merely late.
    const block = source.slice(source.indexOf('const nothingGraded'));
    expect(block.slice(0, 2200)).toMatch(/retryReview\(\)/);
  });

  it('does not poll on its own from this state', () => {
    // Re-reading the session makes the backend attempt generation, and that is
    // a model call (#346). The retry here must stay user-initiated.
    const block = source.slice(source.indexOf('const nothingGraded'));
    expect(block.slice(0, 2200)).not.toMatch(/setInterval|setTimeout/);
  });

  it('keeps the dead endFailed state out', () => {
    // It was never assigned, so every branch that read it was unreachable.
    expect(source).not.toMatch(/endFailed/);
  });
});
