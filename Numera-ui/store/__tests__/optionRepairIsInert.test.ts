/**
 * Re-applying the question already on screen must publish recovered options
 * and change nothing else.
 *
 * repairQuestionOptions (hooks/useDemoTutor.ts) re-fetches the session record
 * and then calls applyBackendPhase with the SAME phase and question, because
 * the options lookup lives inside it. That is only safe because
 * `questionChanged` is false on such a call, so none of the per-question
 * resets run — and those resets include the student's ink, which is what gets
 * submitted. If this ever stops holding, the repair silently wipes the
 * student's working while fixing their options.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionRecord } from '@/lib/api';

const OPTIONS = [
  { option_id: 'A', text: 'Start with 2 and subtract p' },
  { option_id: 'B', text: 'Start with p and subtract 2' },
];

/** A record whose question set knows about Q-T01-007. */
const recordWith = (questionId: string, options: typeof OPTIONS) => ({
  student_model_event: {
    phase_payload: {
      question_set: {
        questions: [{
          question_id: questionId,
          student_view: {
            question_text: 'Which statement correctly describes p - 2?',
            question_type: 'SINGLE_CHOICE',
            options,
            requires_student_response: true,
          },
        }],
      },
    },
  },
}) as unknown as SessionRecord;

const state = () => useNumeraStore.getState();

beforeEach(() => {
  useNumeraStore.setState({
    currentPhase: 'INDEPENDENT_PRACTICE',
    activeQuestionId: 'Q-T01-007',
    questionText: 'Which statement correctly describes p - 2?',
    questionType: 'SINGLE_CHOICE',
    questionOptions: [],
    backendSession: null,
    items: [],
  });
});

describe('the option repair', () => {
  it('publishes the options once the record knows the question', () => {
    // The failing state: the question is on screen, its type says it is a
    // choice, and there is nothing to choose.
    expect(state().questionOptions).toEqual([]);

    state().setBackendSession(recordWith('Q-T01-007', OPTIONS));
    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-T01-007',
      questionText: 'Which statement correctly describes p - 2?',
      questionType: 'SINGLE_CHOICE',
    });

    expect(state().questionOptions).toEqual(OPTIONS);
  });

  it('leaves the student\'s ink alone', () => {
    // The reason this is a test and not a comment: applyBackendPhase clears
    // `items` on a question change, and the repair calls it deliberately.
    const ink = [{ id: 'S1', kind: 'stroke', points: [1, 2, 3, 4] }];
    useNumeraStore.setState({ items: ink as never });

    state().setBackendSession(recordWith('Q-T01-007', OPTIONS));
    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-T01-007',
      questionText: 'Which statement correctly describes p - 2?',
      questionType: 'SINGLE_CHOICE',
    });

    expect(state().items).toEqual(ink);
  });

  it('leaves a pick the student already made alone', () => {
    useNumeraStore.setState({ selectedOptionId: 'B' });

    state().setBackendSession(recordWith('Q-T01-007', OPTIONS));
    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-T01-007',
      questionText: 'Which statement correctly describes p - 2?',
      questionType: 'SINGLE_CHOICE',
    });

    expect(state().selectedOptionId).toBe('B');
  });

  it('changes nothing when the record still does not know the question', () => {
    // A record that came back without the fresh question — degrade to the
    // canvas rather than blanking the screen.
    state().setBackendSession(recordWith('Q-T01-005', OPTIONS));
    state().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-T01-007',
      questionText: 'Which statement correctly describes p - 2?',
      questionType: 'SINGLE_CHOICE',
    });

    expect(state().questionOptions).toEqual([]);
    expect(state().questionText).toBe('Which statement correctly describes p - 2?');
  });
});
