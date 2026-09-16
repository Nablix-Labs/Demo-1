/**
 * The review screen must not be the place a contract change becomes an outage.
 *
 * Every test here is the same shape: the engine sends less than the type
 * promises, and the last screen of the session still renders.
 */

import { describe, it, expect } from 'vitest';
import { reviewCategories, reviewSummaryText, reviewHook } from '@/lib/sessionReview';
import type { SessionReview } from '@/lib/api';

const full = {
  five_category_summary: {
    category_1_strength: 'You spotted the pattern quickly.',
    category_2_first_error: 'The first slip was adding instead of multiplying.',
    category_3_pattern: null,
    category_4_next_practice: 'Two-step rules.',
    category_5_mastery: 'Nearly there.',
  },
  student_facing_summary: 'A good session.',
  b6_hook: 'Next time we look at negatives.',
  call_to_action: 'CONTINUE_PRACTICE',
  voice_delivery_order: [],
  answer_reveal_allowed: false,
  guardrail_passed: true,
} as unknown as SessionReview;

describe('the five categories', () => {
  it('renders the ones with something to say, in order', () => {
    expect(reviewCategories(full).map((c) => c.key)).toEqual([
      'category_1_strength', 'category_2_first_error',
      'category_4_next_practice', 'category_5_mastery',
    ]);
  });

  it('drops a category the session gave no evidence for', () => {
    // 2 and 3 are null by design.
    expect(reviewCategories(full).some((c) => c.key === 'category_3_pattern')).toBe(false);
  });

  it('drops a category that arrived blank', () => {
    // A heading over an empty line reads as the tutor having nothing to say.
    const blank = { ...full, five_category_summary: { ...full.five_category_summary, category_1_strength: '   ' } } as SessionReview;
    expect(reviewCategories(blank).some((c) => c.key === 'category_1_strength')).toBe(false);
  });

  it('renders nothing rather than throwing when the summary is missing', () => {
    // The case that mattered: the screen used to index straight into this.
    expect(reviewCategories({ student_facing_summary: 'hi' } as unknown as SessionReview)).toEqual([]);
  });

  it('renders nothing when the review itself never arrived', () => {
    // Today's reality: no backend response carries `session_review` at all.
    expect(reviewCategories(null)).toEqual([]);
    expect(reviewCategories(undefined)).toEqual([]);
  });

  it('survives a summary that is not an object', () => {
    expect(reviewCategories({ five_category_summary: 'oops' } as unknown as SessionReview)).toEqual([]);
  });
});

describe('the summary sentence', () => {
  it('is the engine\'s when it sent one', () => {
    expect(reviewSummaryText(full)).toBe('A good session.');
  });

  it('is null when blank, so the caller uses its own sentence', () => {
    // Rendered directly, an empty string is a silent hole where the session's
    // one paragraph of feedback should be.
    expect(reviewSummaryText({ ...full, student_facing_summary: '  ' } as SessionReview)).toBeNull();
    expect(reviewSummaryText({} as SessionReview)).toBeNull();
    expect(reviewSummaryText(null)).toBeNull();
  });
});

describe('the closing hook', () => {
  it('is shown when present and dropped when blank', () => {
    expect(reviewHook(full)).toBe('Next time we look at negatives.');
    expect(reviewHook({ ...full, b6_hook: '' } as SessionReview)).toBeNull();
    expect(reviewHook(null)).toBeNull();
  });
});
