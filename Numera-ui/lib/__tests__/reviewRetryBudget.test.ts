/**
 * How hard the review screen is allowed to ask.
 *
 * Asking is not free. Every `GET /session/{id}` on a session in REVIEW makes
 * the backend attempt to materialise the review, and that attempt is an OpenAI
 * call. The first version of the auto-retry polled every 5s for two minutes —
 * 24 model calls per student per visit — and on the evening of 20 Sep 2026,
 * with the account's monthly quota already exhausted, it turned one failed
 * review into 118 `insufficient_quota` errors in ten minutes (VM journal,
 * boot -2, 17:08–17:20 UTC: `review_materialization_attempt_failed` every
 * 5–7 seconds without a break).
 *
 * The screen itself needs a DOM to test. The budget does not, and the budget
 * is the part that cost money — so it is a constant with its own test rather
 * than two numbers inline in a component.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const source = readFileSync(join(process.cwd(), 'app/review/page.tsx'), 'utf8');

/** The waits, read from the page so the test cannot drift from what ships. */
function waits(): number[] {
  const m = source.match(/const REVIEW_RETRY_WAITS_MS = \[([^\]]+)\]/);
  if (!m) throw new Error('REVIEW_RETRY_WAITS_MS not found in app/review/page.tsx');
  return m[1].split(',').map((n) => Number(n.trim().replace(/_/g, ''))).filter(Number.isFinite);
}

describe('the review auto-retry budget', () => {
  it('spends at most six model calls on one visit', () => {
    // One on arrival plus the automatic ones. The old 5s/2min loop spent 24.
    expect(1 + waits().length).toBeLessThanOrEqual(6);
  });

  it('still covers the two minutes a slow generation needs', () => {
    // #326 took 55s to generate. Giving up at 30s would strand that student.
    const total = waits().reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThanOrEqual(110_000);
  });

  it('backs off rather than polling at a fixed rate', () => {
    const w = waits();
    for (let i = 1; i < w.length; i += 1) expect(w[i]).toBeGreaterThan(w[i - 1]);
  });

  it('never asks twice inside four seconds', () => {
    // The floor that stops a tight loop reaching the model at all.
    for (const wait of waits()) expect(wait).toBeGreaterThanOrEqual(4_000);
  });

  it('indexes the waits by attempt, so the backoff is actually applied', () => {
    // The bug this guards: reading the array with a fixed index, or keeping a
    // scalar constant, would restore the flat 5s poll while looking correct.
    expect(source).toMatch(/REVIEW_RETRY_WAITS_MS\[autoRetries\]/);
    expect(source).toMatch(/autoRetries < REVIEW_RETRY_WAITS_MS\.length/);
  });
});
