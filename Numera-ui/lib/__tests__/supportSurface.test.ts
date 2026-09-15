/**
 * Which surface a rung is presented on.
 *
 * Manjusha, 7 Sep: "We have the support ladder like hint 1, hint 2, visual cue
 * — these can be shown as sticky notes ... The rest of the stuff's should come
 * in the canvas. Like scaffolding, parallel ex, tutor solved."
 *
 * The reason is the one her 4 Sep screenshot shows: a worked example is the
 * tutor DOING the maths, and it belongs on the surface the maths is on. Kept
 * in the support column it competed with the student's own working for the
 * same strip of screen, and the column is the wrong shape for it — a
 * walkthrough is wide and long, a hint is a sentence.
 */
import { describe, expect, it } from 'vitest';
import { railRungs, visibleRung, collapsedRungs, type DeckState } from '@/lib/supportDeck';

const base: DeckState = {
  visibleHint: null,
  visualCueVisible: false,
  visualCueDescription: null,
  visualCueAssetUrl: null,
  visualCueId: null,
  supportDeck: [],
  openedRung: null,
  deckCollapsed: false,
  currentPhase: 'GUIDED_PRACTICE',
  rescueSteps: [],
  rescueCompleted: false,
  rescueAdvanceFailure: null,
  guidedRescue: null,
} as unknown as DeckState;

const withHint = (over: Partial<DeckState> = {}): DeckState => ({
  ...base, visibleHint: 'What stays the same?', supportDeck: ['HINT'], ...over,
});

const withRescue = (over: Partial<DeckState> = {}): DeckState => ({
  ...base,
  guidedRescue: { rescue_type: 'TUTOR_SOLVED' },
  supportDeck: ['TUTOR_SOLVED'],
  ...over,
} as unknown as DeckState);

describe('the support column', () => {
  it('holds the hint', () => {
    expect(railRungs(withHint())).toEqual(['HINT']);
    expect(visibleRung(withHint())).toBe('HINT');
  });

  it('never holds a worked example, however it arrived', () => {
    // The regression this file exists for. A rescue in the column sat over the
    // canvas and covered the tutor's own writing.
    expect(railRungs(withRescue())).toEqual([]);
    expect(visibleRung(withRescue())).toBeNull();
  });

  it('does not offer a worked example as an "earlier help" chip either', () => {
    // A chip that reopens a card the column no longer renders is a dead end.
    const state = withRescue({ visibleHint: 'Try grouping them.', supportDeck: ['HINT', 'TUTOR_SOLVED'] });
    expect(collapsedRungs(state)).not.toContain('TUTOR_SOLVED');
  });

  it('chips the hint rather than showing it beside a worked example', () => {
    // The two surfaces are independent, but the ladder is not: the walkthrough
    // is the current rung, so the hint it was escalated past keeps its chip and
    // gives up the card. One offer on screen at a time.
    const state = withRescue({ visibleHint: 'Try grouping them.', supportDeck: ['HINT', 'TUTOR_SOLVED'] });
    expect(visibleRung(state)).toBeNull();
    expect(collapsedRungs(state)).toEqual(['HINT']);
  });
});
