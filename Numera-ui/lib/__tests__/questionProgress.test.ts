import { describe, it, expect } from 'vitest';
import { questionProgress, type SessionRecord } from '@/lib/api';

function record(questionIds: string[] | null): SessionRecord {
  return {
    student_model_event: questionIds
      ? {
          phase_payload: {
            phase: 'GUIDED_PRACTICE',
            payload_type: 'QUESTION_SET',
            question_set: {
              questions: questionIds.map((question_id) => ({
                question_id,
                student_view: { question_text: question_id },
              })),
            },
            orientation_bundle: null,
          },
          journey_state: { topic_id: 'ALG-ORI-02' },
        }
      : null,
  } as unknown as SessionRecord;
}

const SET = ['Q-T01-001', 'Q-T01-002', 'Q-T01-006'];

describe('questionProgress', () => {
  it('locates the current question in the phase set', () => {
    expect(questionProgress(record(SET), 'Q-T01-001')).toEqual({ index: 0, total: 3 });
    expect(questionProgress(record(SET), 'Q-T01-002')).toEqual({ index: 1, total: 3 });
    expect(questionProgress(record(SET), 'Q-T01-006')).toEqual({ index: 2, total: 3 });
  });

  it('reports nothing rather than guessing when there is no question set', () => {
    // A zero total is the rail's signal to hide. Inventing a position is what
    // the old hardcoded "step 3 of 9" did, and it was wrong for every student.
    expect(questionProgress(record(null), 'Q-T01-001')).toEqual({ index: 0, total: 0 });
  });

  it('reports nothing for a question that is not in the set', () => {
    // A bank-served id (the ALG_1STEP_GP_* case) is not in the authored set.
    expect(questionProgress(record(SET), 'ALG_1STEP_GP_F01')).toEqual({ index: 0, total: 0 });
  });

  it('handles a null question id', () => {
    // Orientation has no question of its own.
    expect(questionProgress(record(SET), null)).toEqual({ index: 0, total: 0 });
  });

  it('handles a missing record', () => {
    expect(questionProgress(null, 'Q-T01-001')).toEqual({ index: 0, total: 0 });
    expect(questionProgress(undefined, 'Q-T01-001')).toEqual({ index: 0, total: 0 });
  });

  it('handles an empty set', () => {
    expect(questionProgress(record([]), 'Q-T01-001')).toEqual({ index: 0, total: 0 });
  });
});
