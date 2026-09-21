/**
 * A read of a REVIEW session waits long enough for the backend to BUILD the
 * review inside the request (25–55 s on 21 Sep, #346). At the ordinary 30 s
 * the client gave up mid-build and the retry started another one; the
 * student had to refresh to see a review that had finished behind them.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { REVIEW_READ_TIMEOUT_MS } from '@/lib/reviewReady';

describe('reading a review session', () => {
  it('waits longer than one review build takes', () => {
    expect(REVIEW_READ_TIMEOUT_MS).toBeGreaterThanOrEqual(60_000);
  });

  it('is the timeout the review page actually reads with', () => {
    const page = readFileSync(join(process.cwd(), 'app/review/page.tsx'), 'utf8');
    expect(page).toContain('getSession(id, studentId(), { timeout: REVIEW_READ_TIMEOUT_MS })');
  });
});
