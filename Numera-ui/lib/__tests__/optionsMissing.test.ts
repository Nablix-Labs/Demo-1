/**
 * A choice question with nothing to choose.
 *
 * Manjusha, 29 Aug: "No option" — "Which statement correctly describes n + 6?"
 * rendered in Phase 3 with the four statements missing. The cause is in
 * lib/questionOptions.ts: a Phase 3 reply cannot carry the question set, and
 * Phase 3 serves a fresh question after a wrong answer.
 *
 * These pin the PREDICATE rather than the fetch, because the predicate is what
 * decides whether a request goes on the wire at all — and getting it wrong in
 * the permissive direction means a GET per turn for every free-response
 * question in the app.
 */

import { describe, expect, it } from 'vitest';
import { optionsMissing } from '@/lib/questionOptions';

const option = { option_id: 'A', text: 'Start with p and subtract 2' };

describe('optionsMissing', () => {
  it('is true for a choice question that arrived with none', () => {
    expect(optionsMissing('SINGLE_CHOICE', [])).toBe(true);
  });

  it('covers every question type that cannot be answered without them', () => {
    expect(optionsMissing('CHOICE_WITH_EXPLANATION', [])).toBe(true);
    expect(optionsMissing('TRUE_FALSE_WITH_EXPLANATION', [])).toBe(true);
  });

  it('is false once the options are there', () => {
    expect(optionsMissing('SINGLE_CHOICE', [option])).toBe(false);
  });

  it('is false for a free-response question', () => {
    // The canvas IS the answer channel here. Repairing would put a GET on the
    // wire for every ordinary question in the app.
    expect(optionsMissing('SHORT_RESPONSE', [])).toBe(false);
    expect(optionsMissing('MULTI_PART_SHORT_RESPONSE', [])).toBe(false);
  });

  it('is false when the backend named no type', () => {
    // question_type is NOT stripped in silent mode, so a null one means the
    // backend really did not say — not that the type went missing in transit.
    expect(optionsMissing(null, [])).toBe(false);
    expect(optionsMissing(undefined, undefined)).toBe(false);
  });
});
