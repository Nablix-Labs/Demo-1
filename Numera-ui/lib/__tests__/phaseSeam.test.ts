/**
 * `applyBackendPhase` is the only seam a backend reply may move the phase through.
 *
 * Both answer paths used to follow `syncBackendSession(res)` with a second,
 * bare `setCurrentPhase(res.current_phase)`. Usually harmless — it wrote the
 * same value twice — but `syncBackendSession` deliberately DELAYS the phase
 * commit by REVEAL_MS when the turn both annotated the finished question and
 * moved on, so the tutor's marks can be read before the board clears. The bare
 * call did not wait, so for that window the phase had advanced while the
 * question, options, anchors and locks still belonged to the question just
 * left.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { revealDecision, REVEAL_MS } from '@/lib/revealBeforeClear';

describe('the phase-mutation seam', () => {
  it('has no bare setCurrentPhase on a reply path in useDemoTutor', () => {
    // Read as source text: the invariant is "no second writer", which cannot
    // be observed from outside without a React renderer this suite does not have.
    const src = readFileSync(resolve(process.cwd(), 'hooks/useDemoTutor.ts'), 'utf8');
    expect(src).not.toContain('setCurrentPhase(res.current_phase)');
  });

  it('still holds the phase change back while the marks are read', () => {
    // The behaviour the bare call was racing. Guarded here so removing it
    // cannot be "fixed" later by reinstating an immediate write.
    const held = revealDecision(2, 'Q1', 'Q2');
    expect(held).toEqual({ reveal: true, holdMs: REVEAL_MS });
    // ...and no hold when there is nothing to reveal, so ordinary turns are
    // not delayed.
    expect(revealDecision(0, 'Q1', 'Q2').holdMs).toBe(0);
    expect(revealDecision(2, 'Q1', 'Q1').holdMs).toBe(0);
  });
});
