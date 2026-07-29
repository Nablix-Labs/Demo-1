/**
 * The question on the canvas must survive a conversation.
 *
 * Two failures, pulling in opposite directions, which is why the rule lives in
 * one place:
 *
 *   - Carrying the previous question forward on a phase change left a finished
 *     diagnostic question on screen for the whole orientation (2026-07-28).
 *   - Clearing it whenever a reply omitted the question blanked the canvas
 *     mid-lesson, while the student was still working on it (2026-07-29).
 *
 * The phase is what distinguishes them.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

describe('applyBackendPhase', () => {
  beforeEach(() =>
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      questionText: 'Solve for x: 2x + 5 = 13',
      activeQuestionId: 'Q-1',
    }),
  );

  it('keeps the question when a mid-lesson reply does not restate it', () => {
    // The reported bug: a conversational tutor reply carries no question.
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: null,
      questionText: null,
    });
    expect(state().questionText).toBe('Solve for x: 2x + 5 = 13');
    expect(state().activeQuestionId).toBe('Q-1');
  });

  it('treats an empty string the same as a missing question', () => {
    state().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: null, questionText: '   ' });
    expect(state().questionText).toBe('Solve for x: 2x + 5 = 13');
  });

  it('updates the question when the backend sends a new one', () => {
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-2',
      questionText: 'Solve for x: 3x - 4 = 11',
    });
    expect(state().questionText).toBe('Solve for x: 3x - 4 = 11');
    expect(state().activeQuestionId).toBe('Q-2');
  });

  it('clears the question when the phase moves to one that has none', () => {
    // Orientation has no question; keeping the old one is the 2026-07-28 bug.
    state().applyBackendPhase({
      phase: 'CONCEPT_ORIENTATION',
      questionId: null,
      questionText: null,
    });
    expect(state().questionText).toBe('');
    expect(state().activeQuestionId).toBeNull();
    expect(state().currentPhase).toBe('CONCEPT_ORIENTATION');
  });

  it('keeps the wording verbatim, including a "solve for x" prefix', () => {
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-3',
      questionText: 'A box holds x counters. You add 4 and end up with 9.',
    });
    expect(state().questionText).toBe('A box holds x counters. You add 4 and end up with 9.');
  });
});
