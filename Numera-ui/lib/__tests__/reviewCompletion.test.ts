import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  planReviewCompletion, forgetReviewCompletion, runReviewFinish,
} from '@/lib/reviewCompletion';

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

describe('finishing the review — neither failure may be swallowed', () => {
  const ok = () => Promise.resolve();
  const fails = (msg: string) => () => Promise.reject(new Error(msg));

  it('reports success only when both steps succeed', async () => {
    const calls: string[] = [];
    const out = await runReviewFinish({
      reportCompletion: async () => { calls.push('complete'); },
      endSession: async () => { calls.push('end'); },
    });
    expect(out).toEqual({ ok: true });
    // Completion first: ending marks the session done, and doing that before
    // REVIEW_COMPLETED lands closes a session whose phase never advanced.
    expect(calls).toEqual(['complete', 'end']);
  });

  it('stops before ending when REVIEW_COMPLETED fails', async () => {
    let ended = false;
    const out = await runReviewFinish({
      reportCompletion: fails('boom'),
      endSession: async () => { ended = true; },
    });
    expect(out.ok).toBe(false);
    expect(out.ok === false && out.stage).toBe('complete');
    expect(ended).toBe(false);
  });

  it('surfaces a failed /session/end instead of discarding it', async () => {
    // The defect: `await end().catch(() => undefined)` then navigating away,
    // so a failed end was indistinguishable from a successful one and the
    // student left on a session the backend never closed.
    const out = await runReviewFinish({ reportCompletion: ok, endSession: fails('503') });
    expect(out.ok).toBe(false);
    expect(out.ok === false && out.stage).toBe('end');
  });

  it('carries the failure message so the student is told what to retry', async () => {
    const out = await runReviewFinish({ reportCompletion: ok, endSession: fails('Gateway timeout') });
    expect(out.ok === false && out.message).toContain('Gateway timeout');
  });
});
