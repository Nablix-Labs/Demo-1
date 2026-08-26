import { describe, expect, it } from 'vitest';
import { displayedQuestionNumber } from '@/lib/questionNumber';

const record = (ids: string[]) => ({
  student_model_event: {
    phase_payload: { question_set: { questions: ids.map((id) => ({ question_id: id })) } },
  },
}) as never;

describe('the question badge', () => {
  it('shows the position in the served set, not the running count', () => {
    // The reported bug: the backend increments question_number on every question
    // change, and entering a phase IS a change — so the first question of the
    // set arrives already reading 2.
    expect(displayedQuestionNumber(record(['Q1', 'Q2', 'Q3']), 'Q1', 2)).toBe(1);
  });

  it('counts later questions from the same set', () => {
    expect(displayedQuestionNumber(record(['Q1', 'Q2', 'Q3']), 'Q3', 99)).toBe(3);
  });

  it('falls back to the reported number when the set is not loaded yet', () => {
    // The record arrives separately from the reply. Before it lands there is no
    // set to count against, and the backend's number is better than nothing.
    expect(displayedQuestionNumber(null, 'Q1', 4)).toBe(4);
  });

  it('falls back when the question is not in the set at all', () => {
    expect(displayedQuestionNumber(record(['Q1']), 'Q9', 7)).toBe(7);
  });

  it('shows nothing rather than zero', () => {
    // A badge reading "0" is a claim about which question the student is on,
    // and it is never a true one.
    expect(displayedQuestionNumber(null, 'Q1', 0)).toBeNull();
    expect(displayedQuestionNumber(null, null, null)).toBeNull();
  });
});
