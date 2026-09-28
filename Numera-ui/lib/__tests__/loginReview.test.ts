/**
 * A finished student's results arrive with the login (ST015, live 28 Sep 2026).
 * The fixture is that response's `last_journey_state`, trimmed.
 */

import { describe, expect, it } from 'vitest';
import { loginReviewFrom, skillOutcomeLabel } from '@/lib/loginReview';

const ST015 = {
  topic_id: 'ALG-ORI-03',
  topic_status: 'COMPLETED',
  mastery_status: 'MASTERED',
  current_phase: 'REVIEW',
  phase_payload: {
    phase: 'REVIEW',
    payload_type: 'REVIEW_SUMMARY',
    review_summary: {
      summary_id: 'SUMMARY-007',
      topic_id: 'ALG-ORI-03',
      mastery_status: 'MASTERED',
      micro_skill_results: [
        { micro_skill_id: 'T03.M1', final_status: 'INDEPENDENTLY_VERIFIED', highest_support_used: 'NONE' },
        { micro_skill_id: 'T03.M2', final_status: 'INDEPENDENTLY_VERIFIED', highest_support_used: 'NONE' },
      ],
    },
  },
};

describe('loginReviewFrom', () => {
  it('reads the finished topic from the login response', () => {
    expect(loginReviewFrom(ST015)).toEqual({
      topicId: 'ALG-ORI-03',
      masteryStatus: 'MASTERED',
      topicStatus: 'COMPLETED',
      skills: [
        { id: 'T03.M1', status: 'INDEPENDENTLY_VERIFIED', highestSupport: 'NONE' },
        { id: 'T03.M2', status: 'INDEPENDENTLY_VERIFIED', highestSupport: 'NONE' },
      ],
    });
  });

  it('is null for a student who is not in review', () => {
    expect(loginReviewFrom({ ...ST015, current_phase: 'GUIDED_PRACTICE' })).toBeNull();
  });

  it('never throws on a shape it does not know', () => {
    for (const odd of [null, undefined, 'x', [], {}, { current_phase: 'REVIEW' }, { current_phase: 'REVIEW', phase_payload: { review_summary: { micro_skill_results: 'no' } } }]) {
      expect(loginReviewFrom(odd)).toBeNull();
    }
  });
});

describe('skillOutcomeLabel', () => {
  it('words the known outcomes and tidies unknown ones', () => {
    expect(skillOutcomeLabel('INDEPENDENTLY_VERIFIED')).toBe('Done on your own');
    expect(skillOutcomeLabel('SOMETHING_NEW')).toBe('something new');
  });
});
