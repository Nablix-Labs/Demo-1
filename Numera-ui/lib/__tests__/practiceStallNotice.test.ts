/**
 * A Phase 3 entry with no question is SAID, not shown as "Loading question…".
 *
 * ST008, 21 Sep 2026: GUIDED → INDEPENDENT_PRACTICE with question_id null;
 * 44 voice turns then 500'd on the missing question_id, the session re-read
 * came back in 2ms still without one, and the screen read "Loading question…"
 * for good. The retry must re-read the SAME session — clearing it here would
 * start a new one for the default topic (the other bug in this report).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const page = readFileSync(join(process.cwd(), 'app/practice/page.tsx'), 'utf8');

describe('practice stall notice', () => {
  it('sets a notice when the re-read still leaves no question', () => {
    expect(page).toMatch(/resyncSession\(\)\.finally/);
    expect(page).toMatch(/setStallNotice\("Your practice question hasn't arrived yet\."\)/);
  });
  it('retries by re-reading the session, never by clearing it', () => {
    const i = page.indexOf('stallNotice ? (');
    const block = page.slice(i, i + 700);
    expect(block).toMatch(/void resyncSession\(\)/);
    expect(block).not.toMatch(/clearSessionId/);
  });
  it('clears the notice when a question lands', () => {
    expect(page).toMatch(/setNotice\(null\);\s*\n\s*setStallNotice\(null\);/);
  });
});
