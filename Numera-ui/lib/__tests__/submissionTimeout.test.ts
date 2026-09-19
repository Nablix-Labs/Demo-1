/**
 * #326 — the attempt that ends practice is answered only after the backend has
 * built the review (55s measured, two generation attempts). Timing it out at
 * the 30s default left the server in REVIEW and the student on the question.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, sendInteraction, SUBMISSION_TIMEOUT_MS, type InteractionPayload } from '@/lib/api';

const PAYLOAD: InteractionPayload = {
  session_id: 'SESSION001',
  student_id: 'ST001',
  interaction_type: 'ANSWER_SUBMISSION',
  input_source: 'CHOICE',
  current_phase: 'INDEPENDENT_PRACTICE',
  concept_id: 'ALG_LINEAR_ONE_STEP',
  question_id: 'Q-T01-031',
  hint_count: 0,
  turn_id: 'TURN-1',
};

describe('graded submission timeout', () => {
  afterEach(() => vi.restoreAllMocks());

  it('outlasts the review generation that answers the final attempt', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} } as never);
    await sendInteraction(PAYLOAD);
    expect(post.mock.calls[0][2]).toEqual({ timeout: SUBMISSION_TIMEOUT_MS });
    expect(SUBMISSION_TIMEOUT_MS).toBeGreaterThan(55_000);
  });

  it('leaves ordinary tutoring turns on the default', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} } as never);
    await sendInteraction({ ...PAYLOAD, interaction_type: 'OPTION_SELECTED' });
    expect(post.mock.calls[0]).toHaveLength(2);
  });
});
