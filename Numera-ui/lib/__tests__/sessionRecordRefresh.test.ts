import { describe, expect, it } from 'vitest';
import { carriesQuestionSet, refreshedRecord } from '@/lib/sessionRecordRefresh';
import { hasSelectableOptions } from '@/lib/api';

const withSet = { student_model_event: { phase_payload: { question_set: [{ question_id: 'Q2' }] } } } as never;
const withoutSet = { student_model_event: { phase_payload: {} } } as never;

describe('deciding whether the cached record is stale', () => {
  it('sees a reply that carries a new question set', () => {
    expect(carriesQuestionSet(withSet)).toBe(true);
  });

  it('ignores an event with no set — it carries no options to gain', () => {
    // Overwriting on this would drop the options already held for the current
    // question, which is the failure it exists to prevent.
    expect(carriesQuestionSet(withoutSet)).toBe(false);
    expect(carriesQuestionSet({})).toBe(false);
    expect(carriesQuestionSet(null)).toBe(false);
  });
});

describe('the refreshed record', () => {
  it('merges the event into the record it already had', () => {
    const current = { session_id: 'S1', student_id: 'ST001' };
    const next = refreshedRecord(current, withSet)!;
    expect(next.session_id).toBe('S1');
    expect(next).toHaveProperty('student_model_event');
  });

  it('writes nothing when there is no record to merge into', () => {
    // A record built from an event alone would replace a session with a fragment.
    expect(refreshedRecord(null, withSet)).toBeNull();
  });

  it('writes nothing when the reply carries no new set', () => {
    expect(refreshedRecord({ session_id: 'S1' }, withoutSet)).toBeNull();
  });
});

describe('a question view whose options field went missing', () => {
  it('falls back to free response instead of throwing the screen away', () => {
    // Not defensive programming for its own sake: fields have been removed from
    // responses without notice twice here, and each time it was a live outage.
    expect(hasSelectableOptions({ question_type: 'SINGLE_CHOICE' } as never)).toBe(false);
    expect(hasSelectableOptions({ question_type: 'SINGLE_CHOICE', options: null } as never)).toBe(false);
  });

  it('still shows a chooser when the options are there', () => {
    expect(hasSelectableOptions(
      { question_type: 'SINGLE_CHOICE', options: [{ option_id: 'A', text: 'a' }] } as never,
    )).toBe(true);
  });
});
