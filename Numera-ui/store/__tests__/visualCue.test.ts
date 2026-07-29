/**
 * A visual cue belongs to the question it was raised for.
 *
 * Reported as "why does it show the old visual cue" (Sanya, 2026-07-29). Two
 * separate causes, both here:
 *
 *   - Nothing ever cleared the cue, so one raised on question 1 stayed on
 *     screen through questions 2 and 3 — guidance about work already finished.
 *   - resolveCueCard fell back to a hardcoded default card for any cue_type it
 *     did not recognise, so the student saw a fixed worked example about a
 *     different equation entirely. Covered in visualCueCards.test.ts.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

/** A cue is showing on question Q-1 of guided practice. */
function cueShowingOnQ1() {
  useNumeraStore.setState({
    currentPhase: 'GUIDED_PRACTICE',
    activeQuestionId: 'Q-1',
    questionText: 'Solve for x: 2x + 5 = 13',
    visualCueVisible: true,
    visualCueType: 'EQUATION_BLOCK',
    visualCueDescription: 'Focus on the number added to the x term.',
  });
}

describe('visual cue lifetime', () => {
  beforeEach(cueShowingOnQ1);

  it('clears when the backend moves to a new question', () => {
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-2',
      questionText: 'Solve for x: 3x - 4 = 11',
    });
    expect(state().visualCueVisible).toBe(false);
    expect(state().visualCueType).toBeNull();
    expect(state().visualCueDescription).toBeNull();
  });

  it('clears when the phase changes', () => {
    state().applyBackendPhase({
      phase: 'CONCEPT_ORIENTATION',
      questionId: null,
      questionText: null,
    });
    expect(state().visualCueVisible).toBe(false);
  });

  it('survives a conversational reply on the SAME question', () => {
    // The tutor answering a question about the current problem must not wipe
    // the guidance the student is reading.
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: null,
      questionText: null,
    });
    expect(state().visualCueVisible).toBe(true);
    expect(state().visualCueType).toBe('EQUATION_BLOCK');
  });

  it('survives the backend restating the same question id', () => {
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-1',
      questionText: 'Solve for x: 2x + 5 = 13',
    });
    expect(state().visualCueVisible).toBe(true);
  });
});
