/**
 * When Review may be entered, and how a refused Review is recognised.
 *
 * Both rules used to be inline conditions. The readiness one was
 * `phase3Locked(...)` on the practice screen — "the current question is frozen"
 * — which is not the same claim as "the backend has entered Review", and
 * offered a transition that only full mastery can cause. The failure one did
 * not exist at all: a review that failed to generate arrived as a 200 with a
 * null review and rendered an empty screen.
 */

import { describe, expect, it } from 'vitest';
import {
  reviewIsReady,
  isReviewUnavailable,
  REVIEW_UNAVAILABLE,
} from '@/lib/reviewReady';

describe('reviewIsReady', () => {
  it('is true only when the backend is in Review AND has a review', () => {
    expect(reviewIsReady({ current_phase: 'REVIEW', phase4_review: { tutor_replays: [] } })).toBe(true);
  });

  it('is false in Review with no review — the failed-generation state', () => {
    // The whole bug: entering on current_phase alone renders Phase 4 with
    // nothing in it.
    expect(reviewIsReady({ current_phase: 'REVIEW', phase4_review: null })).toBe(false);
    expect(reviewIsReady({ current_phase: 'REVIEW' })).toBe(false);
  });

  it('is false while the backend is still in Independent Practice', () => {
    // A locked Phase 3 question must not expose Review. Only mastery exits
    // Phase 3, and mastery is the Student Model's call, not the screen's.
    expect(
      reviewIsReady({ current_phase: 'INDEPENDENT_PRACTICE', phase4_review: { tutor_replays: [] } })
    ).toBe(false);
  });

  it('is false for a missing session rather than throwing', () => {
    expect(reviewIsReady(null)).toBe(false);
    expect(reviewIsReady(undefined)).toBe(false);
  });

  it('tolerates the casing and padding a phase string arrives with', () => {
    expect(reviewIsReady({ current_phase: ' review ', phase4_review: {} })).toBe(true);
  });

  it('accepts a review that is falsy but present', () => {
    // An empty object is a payload the adapter can reject on its own terms;
    // absence is the only thing this rule treats as "not ready".
    expect(reviewIsReady({ current_phase: 'REVIEW', phase4_review: {} })).toBe(true);
  });
});

describe('isReviewUnavailable', () => {
  it('recognises the backend code', () => {
    expect(
      isReviewUnavailable({ response: { data: { error_code: REVIEW_UNAVAILABLE } } })
    ).toBe(true);
  });

  it('does not match other failures, which are not retryable the same way', () => {
    expect(isReviewUnavailable({ response: { data: { error_code: 'ADAPTER_UNAVAILABLE' } } })).toBe(false);
    expect(isReviewUnavailable({ response: { data: {} } })).toBe(false);
    expect(isReviewUnavailable(new Error('network'))).toBe(false);
    expect(isReviewUnavailable(null)).toBe(false);
  });

  it('reads error_code, not the message', () => {
    // The backend lifts {code, message} into error_code precisely so the client
    // never has to pattern-match student-facing prose, which gets reworded.
    expect(
      isReviewUnavailable({
        response: { data: { error_code: 'HTTP_ERROR', message: "{'code': 'PHASE4_REVIEW_UNAVAILABLE'}" } },
      })
    ).toBe(false);
  });
});
