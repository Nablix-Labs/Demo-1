/**
 * Reading a question's options off the session record.
 *
 * Options are sent ONCE, on the session record, while `/interaction` replies
 * only ever name the current question. So the lookup by id is the only route
 * from "the backend told us the question moved" to "here is what to choose
 * from" — if it returns nothing, a choice question renders with no way to
 * answer it.
 */

import { describe, it, expect } from 'vitest';
import { studentViewFor, hasSelectableOptions, type SessionRecord } from '@/lib/api';

const view = (over: Partial<{ question_type: string; options: { option_id: string; text: string }[] }> = {}) => ({
  question_text: 'What does x mean in 2x?',
  question_type: 'CHOICE_WITH_EXPLANATION',
  options: [
    { option_id: 'A', text: 'Add 2 and x' },
    { option_id: 'B', text: '2 times x' },
  ],
  requires_student_response: true,
  ...over,
});

const record = (questions: unknown[]): SessionRecord =>
  ({ student_model_event: { phase_payload: { question_set: { questions } } } } as unknown as SessionRecord);

describe('studentViewFor', () => {
  it('finds the view for the question being worked on', () => {
    const rec = record([
      { question_id: 'Q1', student_view: view() },
      { question_id: 'Q2', student_view: view({ question_type: 'SHORT_RESPONSE', options: [] }) },
    ]);
    expect(studentViewFor(rec, 'Q2')?.question_type).toBe('SHORT_RESPONSE');
    expect(studentViewFor(rec, 'Q1')?.options).toHaveLength(2);
  });

  it('returns null rather than guessing when the id is not in the set', () => {
    expect(studentViewFor(record([{ question_id: 'Q1', student_view: view() }]), 'Q9')).toBeNull();
  });

  it('returns null for a phase with no question at all', () => {
    // Orientation. A null id must not match the first question in the set.
    expect(studentViewFor(record([{ question_id: 'Q1', student_view: view() }]), null)).toBeNull();
  });

  it('survives a session that predates the question set', () => {
    expect(studentViewFor({} as SessionRecord, 'Q1')).toBeNull();
    expect(studentViewFor(null, 'Q1')).toBeNull();
  });
});

describe('hasSelectableOptions', () => {
  it.each(['SINGLE_CHOICE', 'CHOICE_WITH_EXPLANATION', 'TRUE_FALSE_WITH_EXPLANATION'])(
    'shows options for %s',
    (question_type) => {
      expect(hasSelectableOptions(view({ question_type }) as never)).toBe(true);
    },
  );

  it.each(['SHORT_RESPONSE', 'MULTI_PART_SHORT_RESPONSE'])(
    'leaves %s as free response',
    (question_type) => {
      expect(hasSelectableOptions(view({ question_type, options: [] }) as never)).toBe(false);
    },
  );

  it('falls back to free response when a choice type arrives with no options', () => {
    // Rendering an empty chooser would leave the student with a question and
    // nothing to answer it with — worse than the plain text box.
    expect(hasSelectableOptions(view({ options: [] }) as never)).toBe(false);
  });

  it('handles a missing view', () => {
    expect(hasSelectableOptions(null)).toBe(false);
  });
});
