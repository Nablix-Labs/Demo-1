import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  api,
  isStaleTurnResponse,
  sendInteraction,
  type InteractionPayload,
} from '@/lib/api';
import {
  sendSynchronizedInteraction,
  syncBackendSession,
} from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

const PAYLOAD: InteractionPayload = {
  session_id: 'SESSION001',
  student_id: 'ST001',
  interaction_type: 'ANSWER_SUBMISSION',
  input_source: 'TEXT',
  text_input: 'n + 5',
  current_phase: 'GUIDED_PRACTICE',
  concept_id: 'ALG_LINEAR_ONE_STEP',
  question_id: 'Q-T01-006',
  hint_count: 0,
  turn_id: 'TURN-UNIQUE',
  previous_tutor_turn_id: 'TUTOR-OLD',
};

describe('interaction turn contract', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns a typed stale-turn contract from an HTTP 409', async () => {
    vi.spyOn(api, 'post').mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 409,
        data: {
          status: 'STALE_TURN',
          accepted_turn_id: null,
          expected_previous_tutor_turn_id: 'TUTOR-CURRENT',
          conversation_action: 'WAIT_FOR_STUDENT',
          attempt_increment: 0,
          retry_safe: false,
          message: 'Use the latest tutor turn.',
        },
      },
    });

    const response = await sendInteraction(PAYLOAD);

    expect(isStaleTurnResponse(response)).toBe(true);
    if (!isStaleTurnResponse(response)) throw new Error('Expected STALE_TURN.');
    expect(response.expected_previous_tutor_turn_id).toBe('TUTOR-CURRENT');
  });

  it('does not reinterpret an unrelated HTTP 409 as turn reconciliation', async () => {
    const conflict = {
      isAxiosError: true,
      response: { status: 409, data: { message: 'No active support.' } },
    };
    vi.spyOn(api, 'post').mockRejectedValue(conflict);

    await expect(sendInteraction(PAYLOAD)).rejects.toBe(conflict);
  });

  it('adopts tutor_turn_id from every accepted interaction response', () => {
    useNumeraStore.setState({ lastTutorTurnId: 'TUTOR-OLD' });

    syncBackendSession({
      current_phase: 'GUIDED_PRACTICE',
      current_question: 'What changes and what stays fixed?',
      question_id: 'Q-T01-006',
      tutor_turn_id: 'TUTOR-NEW',
      expected_student_response: 'ANSWER',
      allow_voice_input: true,
    });

    const state = useNumeraStore.getState();
    expect(state.lastTutorTurnId).toBe('TUTOR-NEW');
    expect(state.expectsStudentResponse).toBe(true);
    expect(state.allowVoiceInput).toBe(true);
  });

  it('retries one unevaluated stale student turn with the same idempotency key', async () => {
    const post = vi.spyOn(api, 'post')
      .mockRejectedValueOnce({
        isAxiosError: true,
        response: {
          status: 409,
          data: {
            status: 'STALE_TURN',
            accepted_turn_id: null,
            expected_previous_tutor_turn_id: 'TUTOR-CURRENT',
            conversation_action: 'WAIT_FOR_STUDENT',
            attempt_increment: 0,
            retry_safe: false,
            message: 'Use the latest tutor turn.',
          },
        },
      })
      .mockResolvedValueOnce({
        data: {
          session_id: 'SESSION001',
          student_id: 'ST001',
          current_phase: 'GUIDED_PRACTICE',
          current_question: 'Write the rule.',
          question_id: 'Q-T01-006',
          interaction_mode: 'VOICE_AND_CANVAS',
          message: 'Now explain what stays fixed.',
          message_voice: 'Now explain what stays fixed.',
          hint_count: 0,
          phase_indicator: 'GUIDED_PRACTICE',
          conversation_action: 'REQUEST_EXPLANATION',
          attempt_increment: 0,
          tutor_turn_id: 'TUTOR-NEXT',
        },
      });

    const response = await sendSynchronizedInteraction(PAYLOAD);

    expect(response.tutor_turn_id).toBe('TUTOR-NEXT');
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1][1]).toMatchObject({
      turn_id: 'TURN-UNIQUE',
      previous_tutor_turn_id: 'TUTOR-CURRENT',
      text_input: 'n + 5',
    });
  });
});
