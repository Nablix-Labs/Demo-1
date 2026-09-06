import { describe, it, expect } from 'vitest';
import {
  deckRungs,
  visibleRung,
  collapsedRungs,
  withRung,
  rungLabel,
  type DeckState,
  type DeckRung,
} from '@/lib/supportDeck';
import type { RescueStep } from '@/lib/rescueActions';

const base: DeckState = {
  visibleHint: null,
  visualCueVisible: false,
  visualCueDescription: null,
  visualCueAssetUrl: null,
  visualCueId: null,
  rescueSteps: [],
  guidedRescue: null,
  currentPhase: 'GUIDED_PRACTICE',
  supportDeck: [],
  openedRung: null,
  deckCollapsed: false,
};

const step = (mode: 'PARALLEL' | 'TUTOR_SOLVED'): RescueStep =>
  ({ actionId: 'a1', rescueId: 'r1', mode, stepIndex: 1 } as RescueStep);

const withHint = (s: DeckState): DeckState => ({ ...s, visibleHint: 'Try grouping the terms.' });
const withCue = (s: DeckState): DeckState =>
  ({ ...s, visualCueVisible: true, visualCueDescription: 'One rule, many cases.' });

describe('deckRungs', () => {
  it('is empty when nothing has been offered', () => {
    expect(deckRungs(base)).toEqual([]);
    expect(visibleRung(base)).toBeNull();
    expect(collapsedRungs(base)).toEqual([]);
  });

  it('keeps the order the rungs were offered in', () => {
    const s = withCue(withHint({ ...base, supportDeck: ['HINT', 'VISUAL_CUE'] }));
    expect(deckRungs(s)).toEqual(['HINT', 'VISUAL_CUE']);
  });

  it('honours arrival order even when it contradicts ladder order', () => {
    // The ladder is documented as backend behaviour, not something the frontend
    // can enforce. If a cue arrives before a hint, "latest" is still the hint.
    const s = withCue(withHint({ ...base, supportDeck: ['VISUAL_CUE', 'HINT'] }));
    expect(deckRungs(s)).toEqual(['VISUAL_CUE', 'HINT']);
    expect(visibleRung(s)).toBe('HINT');
  });

  it('drops a rung whose content has gone, without being told', () => {
    // Order is stored; membership is derived. This is the whole reason the deck
    // does not hold content of its own.
    const s: DeckState = { ...withHint(base), supportDeck: ['HINT', 'VISUAL_CUE'] };
    expect(deckRungs(s)).toEqual(['HINT']);
  });

  it('keeps a live rung the stored order never recorded', () => {
    // Content set by a path that did not record the arrival. Dropping it would
    // hide support that is genuinely on screen.
    const s = withCue(withHint({ ...base, supportDeck: [] }));
    expect(deckRungs(s)).toEqual(['HINT', 'VISUAL_CUE']);
  });

  it('orders unrecorded rungs among themselves by ladder rank', () => {
    const s = withCue(withHint({ ...base, rescueSteps: [step('TUTOR_SOLVED')], supportDeck: [] }));
    expect(deckRungs(s)).toEqual(['HINT', 'VISUAL_CUE', 'TUTOR_SOLVED']);
  });

  it('never lets an unrecorded rung outrank one that was watched arriving', () => {
    // A rung of unknown age must not claim "latest" from a walkthrough that
    // just opened — otherwise a hint already on screen steals the view from the
    // rescue the student was sent to.
    const s = withCue(withHint({
      ...base,
      rescueSteps: [step('TUTOR_SOLVED')],
      supportDeck: ['TUTOR_SOLVED'],
    }));
    expect(deckRungs(s)).toEqual(['HINT', 'VISUAL_CUE', 'TUTOR_SOLVED']);
    expect(visibleRung(s)).toBe('TUTOR_SOLVED');
  });

  it('is empty in Phase 3, whatever arrived', () => {
    // Phase 3 is answered alone (spec §3.2). Agrees with each component's own
    // render gate rather than trusting one of them ran first.
    const s = withCue(withHint({ ...base, currentPhase: 'INDEPENDENT_PRACTICE', supportDeck: ['HINT'] }));
    expect(deckRungs(s)).toEqual([]);
    expect(visibleRung(s)).toBeNull();
  });

  it('needs more than visibility for a cue to count', () => {
    // VisualCue renders nothing with no description and no image, and a chip
    // leading to an empty card is worse than no chip.
    const empty: DeckState = { ...base, visualCueVisible: true, supportDeck: ['VISUAL_CUE'] };
    expect(deckRungs(empty)).toEqual([]);
    const withImage: DeckState = { ...empty, visualCueAssetUrl: 'https://x/y.png' };
    expect(deckRungs(withImage)).toEqual(['VISUAL_CUE']);
  });
});

describe('deckRungs — rescue', () => {
  it('treats both rescue implementations as one rung', () => {
    // The student was offered one worked example, not two. rescueMode still
    // decides which component renders it.
    const s: DeckState = {
      ...base,
      rescueSteps: [step('TUTOR_SOLVED')],
      guidedRescue: { rescue_type: 'PARALLEL_EXAMPLE' } as never,
      supportDeck: ['TUTOR_SOLVED'],
    };
    expect(deckRungs(s)).toEqual(['TUTOR_SOLVED']);
  });

  it('reads the rung from the stepwise mode', () => {
    const s: DeckState = { ...base, rescueSteps: [step('PARALLEL')], supportDeck: ['PARALLEL_EXAMPLE'] };
    expect(deckRungs(s)).toEqual(['PARALLEL_EXAMPLE']);
  });

  it('falls back to the legacy payload when no stepwise rescue exists', () => {
    const s: DeckState = {
      ...base,
      guidedRescue: { rescue_type: 'TUTOR_SOLVED' } as never,
      supportDeck: ['TUTOR_SOLVED'],
    };
    expect(deckRungs(s)).toEqual(['TUTOR_SOLVED']);
  });

  it('demotes the rungs above it instead of destroying them', () => {
    // The change Manjusha asked for. Previously opening a rescue cleared the
    // hint and cue outright, so a student could not re-read the hint.
    const s = withCue(withHint({
      ...base,
      rescueSteps: [step('TUTOR_SOLVED')],
      supportDeck: ['HINT', 'VISUAL_CUE', 'TUTOR_SOLVED'],
    }));
    expect(visibleRung(s)).toBe('TUTOR_SOLVED');
    expect(collapsedRungs(s)).toEqual(['HINT', 'VISUAL_CUE']);
  });
});

describe('visibleRung / collapsedRungs', () => {
  const three = withCue(withHint({
    ...base,
    rescueSteps: [step('TUTOR_SOLVED')],
    supportDeck: ['HINT', 'VISUAL_CUE', 'TUTOR_SOLVED'],
  }));

  it('shows the latest when nothing is opened', () => {
    expect(visibleRung(three)).toBe('TUTOR_SOLVED');
    expect(collapsedRungs(three)).toEqual(['HINT', 'VISUAL_CUE']);
  });

  it('shows the opened chip instead', () => {
    const s = { ...three, openedRung: 'HINT' as DeckRung };
    expect(visibleRung(s)).toBe('HINT');
    expect(collapsedRungs(s)).toEqual(['VISUAL_CUE', 'TUTOR_SOLVED']);
  });

  it('falls back to the latest when the opened rung is stale', () => {
    // The student opened a hint; the backend then cleared it. An empty lane is
    // not an answer to "show me that again".
    const s: DeckState = { ...three, visibleHint: null, openedRung: 'HINT' };
    expect(visibleRung(s)).toBe('TUTOR_SOLVED');
  });

  it('shows nothing but keeps every chip once the student puts the card away', () => {
    // The X closes the card; it does not delete the rung. One click on the chip
    // brings it back, which is the half of Manjusha's ask that a plain dismiss
    // would have lost.
    const s: DeckState = { ...three, deckCollapsed: true };
    expect(visibleRung(s)).toBeNull();
    expect(collapsedRungs(s)).toEqual(['HINT', 'VISUAL_CUE', 'TUTOR_SOLVED']);
  });

  it('leaves no chips when only one rung is held', () => {
    const s = withHint({ ...base, supportDeck: ['HINT'] });
    expect(visibleRung(s)).toBe('HINT');
    expect(collapsedRungs(s)).toEqual([]);
  });
});

describe('withRung', () => {
  it('appends a rung that is new', () => {
    expect(withRung(['HINT'], 'VISUAL_CUE')).toEqual(['HINT', 'VISUAL_CUE']);
  });

  it('moves a re-sent rung to the latest position', () => {
    // It has just been offered. Keeping its first position would leave a
    // re-sent hint buried behind the cue that superseded it.
    expect(withRung(['HINT', 'VISUAL_CUE'], 'HINT')).toEqual(['VISUAL_CUE', 'HINT']);
  });

  it('cannot grow past one entry per rung', () => {
    let deck: DeckRung[] = [];
    for (let i = 0; i < 20; i += 1) deck = withRung(deck, 'HINT');
    expect(deck).toEqual(['HINT']);
  });
});

describe('rungLabel', () => {
  it('names every rung', () => {
    const rungs: DeckRung[] = ['HINT', 'VISUAL_CUE', 'PARALLEL_EXAMPLE', 'TUTOR_SOLVED'];
    rungs.forEach((r) => expect(rungLabel(r)).toBeTruthy());
    // Matches the titles the rescue components already use, so a chip and the
    // card it opens do not call the same thing two different names.
    expect(rungLabel('PARALLEL_EXAMPLE')).toBe('A similar one');
    expect(rungLabel('TUTOR_SOLVED')).toBe('Let me show you');
  });
});
