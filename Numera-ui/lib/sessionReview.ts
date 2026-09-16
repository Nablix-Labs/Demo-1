/**
 * Reading the engine's end-of-session review without trusting its shape.
 *
 * `session_review` is documented as arriving on `/session/end`, and today no
 * backend response model carries it — `SessionResponse` has no such field, so
 * `sessionReview` is null for every real session and the five categories have
 * never once been on screen. The screen falls back to a sentence it builds
 * from outcome counts, which is why nobody has noticed.
 *
 * That is a backend gap, not something this file can fix. What it can fix is
 * the landing: the screen used to index straight into
 * `review.five_category_summary[key]`, so the day a partial review DOES arrive
 * — the engine sending the summary without the categories, or the field
 * arriving under a different name — the last screen of the session throws
 * instead of rendering. Sanya's deletes have become live outages this way
 * before.
 *
 * So everything here treats every field as missing until proven otherwise, and
 * an absent category is simply not rendered. A review screen with four
 * categories tells the student something; a review screen that crashed tells
 * them their session was lost.
 */

import type { SessionReview } from '@/lib/api';

/** The five categories in the order §5.8 renders them. */
const CATEGORY_LABELS: [string, string][] = [
  ['category_1_strength', 'Strength'],
  ['category_2_first_error', 'First error'],
  ['category_3_pattern', 'Pattern'],
  ['category_4_next_practice', 'Next practice'],
  ['category_5_mastery', 'Mastery'],
];

export interface ReviewCategory {
  key: string;
  label: string;
  text: string;
}

/**
 * The categories that actually have something to say.
 *
 * Categories 2 and 3 are null by design when the session gave no evidence for
 * them, and the rest are dropped on the same rule rather than a separate one:
 * a category with no text renders as a heading over an empty line, which reads
 * as the tutor having nothing to say about the student's strengths.
 */
export function reviewCategories(
  review: SessionReview | null | undefined,
): ReviewCategory[] {
  const summary = review?.five_category_summary;
  if (!summary || typeof summary !== 'object') return [];
  const out: ReviewCategory[] = [];
  for (const [key, label] of CATEGORY_LABELS) {
    const text = (summary as unknown as Record<string, unknown>)[key];
    if (typeof text === 'string' && text.trim()) out.push({ key, label, text });
  }
  return out;
}

/**
 * The engine's own summary sentence, or null to use the caller's fallback.
 *
 * Blank counts as absent. Rendered directly, an empty string is a silent hole
 * where the session's one paragraph of feedback should be — and the caller
 * already has a sentence built from the outcome counts for exactly this case.
 */
export function reviewSummaryText(
  review: SessionReview | null | undefined,
): string | null {
  const text = review?.student_facing_summary;
  return typeof text === 'string' && text.trim() ? text : null;
}

/** The closing hook, when the engine sent one worth showing. */
export function reviewHook(review: SessionReview | null | undefined): string | null {
  const hook = review?.b6_hook;
  return typeof hook === 'string' && hook.trim() ? hook : null;
}
