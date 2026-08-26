import { beforeEach, describe, expect, it, vi } from 'vitest';
import { planReviewCompletion, forgetReviewCompletion } from '@/lib/reviewCompletion';

beforeEach(() => forgetReviewCompletion());

describe('reporting a finished review', () => {
  it('sends once for a session', () => {
    expect(planReviewCompletion('S1', () => 'T1').send).toBe(true);
  });

  it('does not send again when the student leaves the review a second time', () => {
    // REVIEW_COMPLETED advances the journey. The screen has four ways out and
    // can be returned to, so "call it on the way out" fires repeatedly.
    planReviewCompletion('S1', () => 'T1');
    expect(planReviewCompletion('S1', () => 'T2').send).toBe(false);
  });

  it('keeps the original turn id on a repeat, so the backend can dedupe it', () => {
    // The backend derives its request id from the turn id. A fresh turn id per
    // attempt would defeat that and make every exit a new completion event.
    planReviewCompletion('S1', () => 'T1');
    expect(planReviewCompletion('S1', () => 'T2').turnId).toBe('T1');
  });

  it('mints the turn id only when it is actually going to send', () => {
    const mint = vi.fn(() => 'T1');
    planReviewCompletion('S1', mint);
    planReviewCompletion('S1', mint);
    expect(mint).toHaveBeenCalledTimes(1);
  });

  it('reports a different session separately', () => {
    planReviewCompletion('S1', () => 'T1');
    expect(planReviewCompletion('S2', () => 'T2').send).toBe(true);
  });

  it('stays quiet with no session — the demo and offline case, not an error', () => {
    expect(planReviewCompletion(null, () => 'T1').send).toBe(false);
    expect(planReviewCompletion('   ', () => 'T1').send).toBe(false);
  });
});
