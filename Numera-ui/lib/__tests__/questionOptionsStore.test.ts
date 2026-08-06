/**
 * Options through applyBackendPhase.
 *
 * Both transports go through that one action, so this is where a question's
 * shape either survives a phase change or gets lost. The cases that matter are
 * the ones where the reply is PARTIAL: mid-lesson replies routinely carry no
 * question and no type, and treating those as "no options" blanked a choice
 * question into a free-response one while the student was still on it.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionRecord } from '@/lib/api';

const OPTIONS = [
  { option_id: 'A', text: 'Add 2 and x' },
  { option_id: 'B', text: '2 times x' },
];

const RECORD = {
  student_model_event: {
    phase_payload: {
      question_set: {
        questions: [
          {
            question_id: 'Q1',
            student_view: {
              question_text: 'What does x mean in 2x?',
              question_type: 'CHOICE_WITH_EXPLANATION',
              options: OPTIONS,
              requires_student_response: true,
            },
          },
          {
            question_id: 'Q2',
            student_view: {
              question_text: 'Solve x + 3 = 7',
              question_type: 'SHORT_RESPONSE',
              options: [],
              requires_student_response: true,
            },
          },
        ],
      },
    },
  },
} as unknown as SessionRecord;

const store = () => useNumeraStore.getState();

describe('applyBackendPhase — question shape', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      backendSession: RECORD,
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: null,
      questionType: null,
      questionOptions: [],
      selectedOptionId: null,
    });
  });

  it('picks up the options for the question the backend named', () => {
    store().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q1',
      questionText: 'What does x mean in 2x?',
      questionType: 'CHOICE_WITH_EXPLANATION',
    });
    expect(store().questionOptions).toEqual(OPTIONS);
    expect(store().questionType).toBe('CHOICE_WITH_EXPLANATION');
  });

  it('falls back to the record when the reply sent no type', () => {
    store().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q1',
      questionText: 'What does x mean in 2x?',
    });
    expect(store().questionType).toBe('CHOICE_WITH_EXPLANATION');
  });

  it('keeps the current options when a mid-lesson reply names no question', () => {
    store().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q1',
      questionText: 'What does x mean in 2x?',
    });
    // A conversational turn: same phase, no question, no type.
    store().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: null,
      questionText: null,
    });
    expect(store().questionOptions).toEqual(OPTIONS);
    expect(store().questionType).toBe('CHOICE_WITH_EXPLANATION');
  });

  it('swaps to the next question’s shape, options and all', () => {
    store().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q1', questionText: 'a' });
    store().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q2',
      questionText: 'Solve x + 3 = 7',
      questionType: 'SHORT_RESPONSE',
    });
    expect(store().questionOptions).toEqual([]);
    expect(store().questionType).toBe('SHORT_RESPONSE');
  });

  it('drops the pick when the question moves', () => {
    store().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q1', questionText: 'a' });
    store().setSelectedOption('B');
    store().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q2', questionText: 'b' });
    // Otherwise the next question opens with an answer already chosen.
    expect(store().selectedOptionId).toBeNull();
  });

  it('clears options entering a phase that has no question', () => {
    store().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q1', questionText: 'a' });
    store().applyBackendPhase({ phase: 'ORIENTATION', questionId: null, questionText: null });
    expect(store().questionOptions).toEqual([]);
    expect(store().questionType).toBeNull();
  });
});
