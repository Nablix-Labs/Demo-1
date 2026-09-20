/**
 * The margin shows the scaffold as a path (Manav, 20 Sep 2026 — direction D).
 *
 * The one rule that matters here is the contract's: `total_scaffold_steps` is
 * "a progress indicator, NOT permission to reveal later ones". So these pin
 * both halves — steps already shown are remembered, and steps not yet shown
 * carry no text, however many the total says there are.
 */

import { describe, it, expect } from 'vitest';
import { rememberScaffoldStep, trailRows, type SeenScaffoldStep } from '@/lib/scaffoldTrail';
import type { ActiveScaffold } from '@/lib/api';

const step = (n: number, text: string, scaffoldId = 'SC-1'): ActiveScaffold => ({
  scaffoldId,
  currentStepId: `${scaffoldId}-ST-${n}`,
  stepNumber: n,
  stepText: text,
  stepVoice: null,
  totalSteps: 4,
});

const walk = (...steps: ActiveScaffold[]): SeenScaffoldStep[] => {
  let seen: SeenScaffoldStep[] = [];
  let prev: ActiveScaffold | null = null;
  for (const s of steps) {
    seen = rememberScaffoldStep(seen, prev, s);
    prev = s;
  }
  return seen;
};

describe('remembering what has been shown', () => {
  it('keeps each step as it arrives', () => {
    const seen = walk(step(1, 'What changes?'), step(2, 'What stays the same?'));
    expect(seen.map((s) => s.stepText)).toEqual(['What changes?', 'What stays the same?']);
  });

  it('does not duplicate a step the backend re-sends', () => {
    // A turn that did not advance repeats the current step.
    const seen = walk(step(1, 'What changes?'), step(1, 'What changes?'));
    expect(seen).toHaveLength(1);
  });

  it('takes the newer wording when a step is re-sent reworded', () => {
    const seen = walk(step(1, 'What changes?'), step(1, 'Which part changes?'));
    expect(seen.map((s) => s.stepText)).toEqual(['Which part changes?']);
  });

  it('starts a fresh trail for a different scaffold', () => {
    const seen = walk(
      step(1, 'What changes?'),
      step(2, 'What stays the same?'),
      step(1, 'What is the total?', 'SC-2'),
    );
    expect(seen.map((s) => s.stepText)).toEqual(['What is the total?']);
  });

  it('empties when the panel closes', () => {
    const seen = rememberScaffoldStep(walk(step(1, 'What changes?')), step(1, 'What changes?'), null);
    expect(seen).toEqual([]);
  });

  it('reads down the margin in teaching order, not arrival order', () => {
    const seen = walk(step(1, 'What changes?'), step(3, 'Which operation?'), step(2, 'What stays?'));
    expect(seen.map((s) => s.stepNumber)).toEqual([1, 2, 3]);
  });
});

describe('the rows the margin draws', () => {
  it('marks the current step and ticks off the ones before it', () => {
    const seen = walk(step(1, 'What changes?'), step(2, 'What stays the same?'));
    const rows = trailRows(seen, step(2, 'What stays the same?'));
    expect(rows.map((r) => r.state)).toEqual(['done', 'current', 'pending', 'pending']);
  });

  it('NEVER carries text for a step that has not been shown', () => {
    // The contract's rule. A pending row is a number and nothing else.
    const rows = trailRows(walk(step(1, 'What changes?')), step(1, 'What changes?'));
    for (const row of rows.filter((r) => r.state === 'pending')) {
      expect(Object.values(row).every((v) => typeof v !== 'string' || v === 'pending')).toBe(true);
    }
  });

  it('draws one row per step the backend counted', () => {
    const rows = trailRows(walk(step(1, 'What changes?')), step(1, 'What changes?'));
    expect(rows.map((r) => r.stepNumber)).toEqual([1, 2, 3, 4]);
  });

  it('shows the current step after a reload, before any trail exists', () => {
    const rows = trailRows([], step(3, 'Which operation?'));
    expect(rows.find((r) => r.state === 'current')).toMatchObject({
      stepNumber: 3, stepText: 'Which operation?',
    });
    expect(rows).toHaveLength(4);
  });

  it('draws nothing at all when the panel is closed', () => {
    expect(trailRows(walk(step(1, 'What changes?')), null)).toEqual([]);
  });

  it('never draws fewer rows than it has been given steps for', () => {
    // A backend that under-counts must not make a shown step disappear.
    const seen = walk(step(1, 'a'), step(2, 'b'), step(3, 'c'));
    const rows = trailRows(seen, { ...step(3, 'c'), totalSteps: 1 });
    expect(rows).toHaveLength(3);
  });

  it('cannot be spun by an absurd total', () => {
    expect(trailRows([], { ...step(1, 'a'), totalSteps: 100_000 })).toHaveLength(24);
  });
});
