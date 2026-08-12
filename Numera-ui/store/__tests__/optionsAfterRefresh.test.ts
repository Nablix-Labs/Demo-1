/**
 * A choice question must keep its choices across a refresh.
 *
 * Manjusha, 13 Aug 2026: "Which is the general rule:" rendered with no options
 * under it — intermittently, and only after a refresh.
 *
 * Options never travel on an interaction reply; they are looked up out of the
 * session record by question id. A reload drops that record, so whether the
 * options survive depended on whether the record or the first reply landed
 * first. Lose that race and `questionOptions` is set to [] — and nothing ever
 * put them back, because every later reply is for the same question and so
 * leaves the empty list alone. The student is left with a question and no way
 * to answer it.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionRecord } from '@/lib/api';

const OPTIONS = [
  { option_id: 'A', text: '12 + 4' },
  { option_id: 'B', text: 'n + 4' },
];

/** A record carrying the choice question and its options. */
const record = () => ({
  session_id: 'SESSION1',
  current_phase: 'GUIDED_PRACTICE',
  current_question: 'Which is the general rule:',
  question_id: 'Q-T01-004',
  student_model_event: {
    phase_payload: {
      question_set: {
        questions: [
          {
            question_id: 'Q-T01-004',
            student_view: {
              question_type: 'CHOICE_WITH_EXPLANATION',
              options: OPTIONS,
            },
          },
        ],
      },
    },
  },
}) as unknown as SessionRecord;

describe('options survive the record arriving late', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      backendSession: null,
      questionOptions: [],
      questionType: null,
      activeQuestionId: null,
      questionText: '',
      currentPhase: 'GUIDED_PRACTICE',
    });
  });

  it('recovers the options when the reply lands BEFORE the record — the reported bug', () => {
    const s = useNumeraStore.getState();
    // Reply first: no record to look options up in, so they end up empty.
    s.applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-004',
      questionText: 'Which is the general rule:',
    });
    expect(useNumeraStore.getState().questionOptions).toEqual([]);

    // Record arrives a moment later; the choices must come back.
    useNumeraStore.getState().setBackendSession(record());
    expect(useNumeraStore.getState().questionOptions).toEqual(OPTIONS);
    expect(useNumeraStore.getState().questionType).toBe('CHOICE_WITH_EXPLANATION');
  });

  it('still works in the ordinary order — record first, then the reply', () => {
    const s = useNumeraStore.getState();
    s.setBackendSession(record());
    s.applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-004',
      questionText: 'Which is the general rule:',
    });
    expect(useNumeraStore.getState().questionOptions).toEqual(OPTIONS);
  });

  it('does not overwrite options the client already has', () => {
    // A record refetched mid-question must not disturb a live chooser.
    useNumeraStore.setState({ activeQuestionId: 'Q-T01-004', questionOptions: OPTIONS });
    useNumeraStore.getState().setBackendSession(record());
    expect(useNumeraStore.getState().questionOptions).toEqual(OPTIONS);
  });

  it('adds no options to a free-response question', () => {
    useNumeraStore.setState({ activeQuestionId: 'Q-T01-999' });
    useNumeraStore.getState().setBackendSession(record());
    expect(useNumeraStore.getState().questionOptions).toEqual([]);
  });

  it('renders no chooser when the type expects options but none were sent', () => {
    // An empty chooser is worse than free response: a question with no answers.
    const empty = record() as unknown as { student_model_event: { phase_payload: { question_set: { questions: Array<{ student_view: { options: unknown[] } }> } } } };
    empty.student_model_event.phase_payload.question_set.questions[0].student_view.options = [];
    useNumeraStore.setState({ activeQuestionId: 'Q-T01-004' });
    useNumeraStore.getState().setBackendSession(empty as unknown as SessionRecord);
    expect(useNumeraStore.getState().questionOptions).toEqual([]);
  });
});
