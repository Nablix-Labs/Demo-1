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

  it('clears the working when the question changes', () => {
    // Row 32, 11 Aug: nothing cleared student ink on a question change, so the
    // next question opened underneath the last one's solution — and since the
    // canvas is what gets submitted, the OCR then read both answers at once.
    useNumeraStore.setState({
      activeQuestionId: 'Q-1',
      items: [{ id: 'i1', kind: 'line', points: [0, 0, 5, 5] }] as never,
      undone: [{ id: 'i0', kind: 'line', points: [1, 1, 2, 2] }] as never,
      tutorElements: [{ id: 't1', kind: 'line', points: [0, 0, 1, 1] }] as never,
    });

    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-2',
      questionText: 'Next one: 7 + 5',
    });

    expect(state().items).toEqual([]);
    expect(state().undone).toEqual([]);
    expect(state().tutorElements).toEqual([]);
  });

  it('leaves the working alone while the student is on the same question', () => {
    // The opposite failure, and the more damaging one: a conversational reply
    // that omits the question must not wipe work in progress.
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-1',
      items: [{ id: 'i1', kind: 'line', points: [0, 0, 5, 5] }] as never,
    });

    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: null,
      questionText: null,
    });

    expect(state().items).toHaveLength(1);
  });

  it('releases a Phase 3 lock when the rescue question arrives', () => {
    // Phase 3 spec §3.4: "Clear the previous lock only for the new question ID."
    useNumeraStore.setState({
      currentPhase: 'INDEPENDENT_PRACTICE',
      activeQuestionId: 'Q-3',
      phase3LockedQuestionId: 'Q-3',
    });

    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-3-RESCUE',
      questionText: 'Try this one instead',
    });

    expect(state().phase3LockedQuestionId).toBeNull();
  });

  it('drops the previous phase’s options when the phase moves', () => {
    // Manjusha, 8 Aug: the canvas asked the Phase 2 question (3 + 5, 9 + 5,
    // 14 + 5) while the choices below it were still the diagnostic's
    // (2 + 4, 7 + 4, 12 + 4). The options were written by one screen and never
    // cleared by the next, so they outlived the question they belonged to.
    useNumeraStore.setState({
      currentPhase: 'DIAGNOSTIC',
      questionText: 'Which is the general rule?',
      activeQuestionId: 'Q-D1',
      questionType: 'SINGLE_CHOICE',
      questionOptions: [
        { option_id: 'A', text: '12 + 4' },
        { option_id: 'B', text: 'n + 4' },
      ],
      selectedOptionId: 'B',
    });

    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-001',
      questionText: '3 + 5, 9 + 5, 14 + 5 — what is the general rule?',
    });

    expect(state().questionOptions).toEqual([]);
    expect(state().selectedOptionId).toBeNull();
  });
});
