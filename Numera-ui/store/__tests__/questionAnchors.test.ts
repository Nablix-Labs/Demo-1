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

/**
 * A confirmed label has to outlive the turn it was written on (#321).
 *
 * The tutor writes `m → changes` onto the token because the student said so.
 * The next reply carries the question's plain base anchors, as every reply
 * does, and that used to replace the array and take the label with it — so a
 * confirmation the student had just earned was gone by the time they answered.
 */
describe('confirmed anchor state across turns on one question', () => {
  const BASE = [{ token_id: 'T1', text: 'n', char_start: 12, char_end: 13, label: null }];

  // Unique per call: the de-duplication window for action ids is module-level
  // and outlives a single test, so a reused id is silently dropped as a
  // re-delivery.
  let nth = 0;
  const label = (text: string) => ({
    action_id: `A-${(nth += 1)}`,
    type: 'INSERT_LABEL' as const,
    target_kind: 'QUESTION_ANCHOR' as const,
    target_object_id: 'T1',
    confirmed_component_id: null,
    text,
    source_id: null,
    answer_reveal_allowed: false,
  });

  beforeEach(() => useNumeraStore.setState({
    questionAnchors: [], activeQuestionId: 'Q1', currentPhase: 'GUIDED_PRACTICE',
    questionText: 'Ravi scores n points and then scores 4 more.', backendSession: null,
    tutorElements: [], canvasEvents: [],
  }));

  it('survives the next turn\'s base anchors', () => {
    state().setQuestionAnchors(BASE);
    state().applyTutorCanvasActions([label('m → changes')]);
    expect(state().questionAnchors[0].label).toBe('m → changes');

    state().setQuestionAnchors(BASE);
    expect(state().questionAnchors[0].label).toBe('m → changes');
    expect(state().questionAnchors[0].highlighted).toBe(true);
  });

  it('survives a turn that points at nothing', () => {
    // The ordinary reply. Most turns carry no anchors at all.
    state().setQuestionAnchors(BASE);
    state().applyTutorCanvasActions([label('m → changes')]);
    state().setQuestionAnchors([]);
    expect(state().questionAnchors).toHaveLength(1);
    expect(state().questionAnchors[0].label).toBe('m → changes');
  });

  it('still clears when the question changes', () => {
    // The offsets belong to the question that is leaving. This is the one
    // clear, and the merge must not weaken it.
    state().setQuestionAnchors(BASE);
    state().applyTutorCanvasActions([label('m → changes')]);
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q2',
      questionText: 'A different question entirely.', questionType: null,
    });
    expect(state().questionAnchors).toEqual([]);
  });

  it('does not keep a bare highlight the tutor has moved on from', () => {
    // Unconfirmed pointing is still transient — it clears, or it reads as
    // "keep looking here" for the rest of the question.
    state().setQuestionAnchors([{ ...BASE[0], highlighted: true }]);
    state().setQuestionAnchors([]);
    expect(state().questionAnchors).toEqual([]);
  });
});
