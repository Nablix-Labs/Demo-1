/**
 * Anchors are raw character offsets into ONE question's text.
 *
 * That makes them uniquely dangerous to carry across a question change: an
 * offset that pointed at the variable in the last question points at whatever
 * character happens to sit there in the next one, and it will look deliberate.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

const ANCHORS = [{ token_id: 'T1', text: 'n', char_start: 12, char_end: 13, label: 'changes' }];

describe('question anchors in the store', () => {
  beforeEach(() => useNumeraStore.setState({
    questionAnchors: [], activeQuestionId: 'Q1', currentPhase: 'GUIDED_PRACTICE',
    backendSession: null,
  }));

  it('holds what the backend sent, unresolved', () => {
    // Stored as offsets, not as anything positioned: the renderer is what knows
    // which fragment of the question it is drawing.
    state().setQuestionAnchors(ANCHORS);
    expect(state().questionAnchors).toEqual(ANCHORS);
  });

  it('clears them when the question changes', () => {
    state().setQuestionAnchors(ANCHORS);
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q2',
      questionText: 'A different question entirely.', questionType: null,
    });
    expect(state().questionAnchors).toEqual([]);
  });

  it('clears them when the phase changes', () => {
    state().setQuestionAnchors(ANCHORS);
    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE', questionId: 'Q1',
      questionText: 'Same question, new phase.', questionType: null,
    });
    expect(state().questionAnchors).toEqual([]);
  });

  it('keeps them across an ordinary turn on the same question', () => {
    // The tutor talks several times about one question; the highlight it put up
    // must survive those turns or it flickers away mid-explanation.
    state().setQuestionAnchors(ANCHORS);
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q1',
      questionText: 'Ravi scores n points and then scores 4 more.', questionType: null,
    });
    expect(state().questionAnchors).toEqual(ANCHORS);
  });
});
