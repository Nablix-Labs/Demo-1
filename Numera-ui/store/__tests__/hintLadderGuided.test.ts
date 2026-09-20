/**
 * The guided-practice hint card keeps every hint for the question.
 *
 * Sanya, 21 Sep 2026: "it is not displaying the hint 1 and 2 correctly". The
 * store held one `visibleHint`, so each rung overwrote the last and the HINT
 * chip could only ever reopen hint 3. `lib/hintHistory` fixed this for
 * independent practice on 15 Sep; guided practice reads `visibleHints` now.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

beforeEach(() => {
  useNumeraStore.setState({
    visibleHint: null, visibleHints: [], supportDeck: [], openedRung: null, deckCollapsed: false,
    activeQuestionId: 'Q-T01-001', currentPhase: 'GUIDED_PRACTICE',
  });
});

describe('visibleHints', () => {
  it('keeps hints 1, 2 and 3 in order', () => {
    state().setVisibleHint('Look at what changes.');
    state().setVisibleHint('Which number is fixed?');
    state().setVisibleHint('Write the fixed number after the letter.');
    expect(state().visibleHints).toEqual([
      'Look at what changes.',
      'Which number is fixed?',
      'Write the fixed number after the letter.',
    ]);
    expect(state().visibleHint).toBe('Write the fixed number after the letter.');
  });

  it('does not stack a replay of the current hint', () => {
    state().setVisibleHint('Look at what changes.');
    state().setVisibleHint('Look at what changes.');
    expect(state().visibleHints).toHaveLength(1);
  });

  it('clearing the hint keeps the ladder for the chip', () => {
    state().setVisibleHint('Look at what changes.');
    state().setVisibleHint(null);
    expect(state().visibleHints).toEqual(['Look at what changes.']);
  });

  it('starts over on the next question', () => {
    state().setVisibleHint('Look at what changes.');
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-002', questionText: 'Next.', questionType: null,
    });
    expect(state().visibleHints).toEqual([]);
    expect(state().visibleHint).toBeNull();
  });
});
