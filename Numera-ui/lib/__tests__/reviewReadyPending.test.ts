import { describe, expect, it } from 'vitest';
import { reviewReadPending } from '@/lib/reviewReady';

const base = {
  apiEnabled: true,
  hasReviewSession: false,
  reviewReady: false,
  sessionId: null as string | null,
  hasBackendSession: false,
  endedSessionId: null as string | null,
};

describe('knowing that the review is not known yet', () => {
  it('waits while a live session is being read', () => {
    expect(reviewReadPending({ ...base, hasReviewSession: true })).toBe(true);
  });

  it('waits while an ended session is being restored after a refresh', () => {
    // The path that still flashed after the first fix: sessionId is cleared on
    // the way out, so the mount read has no id and only the restore runs.
    expect(reviewReadPending({ ...base, endedSessionId: 'S1' })).toBe(true);
  });

  it('does not wait once the record already carries a review', () => {
    expect(reviewReadPending({
      ...base, hasReviewSession: true, reviewReady: true,
    })).toBe(false);
  });

  it('does not wait once the restore has produced a record', () => {
    expect(reviewReadPending({
      ...base, endedSessionId: 'S1', hasBackendSession: true,
    })).toBe(false);
  });

  it('never waits in mock mode', () => {
    // The demo review must render exactly as it always has.
    expect(reviewReadPending({
      ...base, apiEnabled: false, hasReviewSession: true, endedSessionId: 'S1',
    })).toBe(false);
  });

  it('does not wait when there is nothing to read at all', () => {
    expect(reviewReadPending(base)).toBe(false);
  });
});
