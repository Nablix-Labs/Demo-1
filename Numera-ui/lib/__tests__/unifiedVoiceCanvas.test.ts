import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, sendInteraction, type InteractionPayload } from '@/lib/api';

describe('unified voice canvas interaction', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends one frozen PNG and stroke payload to interaction', async () => {
    const payload: InteractionPayload = {
      session_id: 'SESSION001',
      student_id: 'ST001',
      interaction_type: 'ANSWER_SUBMISSION',
      input_source: 'VOICE',
      voice_transcript: 'Is this right?',
      transcript_confidence: 0.95,
      transcript_final: true,
      turn_id: 'TURN-VOICE-1',
      current_phase: 'GUIDED_PRACTICE',
      concept_id: 'ALG_LINEAR_ONE_STEP',
      question_id: 'Q-T02-004',
      hint_count: 0,
      canvas_state: {
        snapshot_data_url: 'data:image/png;base64,c25hcHNob3Q=',
        strokes: [
          {
            stroke_id: 'stroke-1',
            tool: 'pen',
            points: [{ x: 0.1, y: 0.2 }, { x: 0.2, y: 0.3 }],
            width: 0.01,
          },
        ],
        captured_at: '2026-08-10T10:00:00.000Z',
      },
    };
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} } as never);

    await sendInteraction(payload);

    expect(post).toHaveBeenCalledOnce();
    expect(post).toHaveBeenCalledWith('/interaction', payload);
  });
});
