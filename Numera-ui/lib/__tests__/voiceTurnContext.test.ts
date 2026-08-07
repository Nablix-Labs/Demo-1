import { describe, it, expect } from 'vitest';
import { turnContextFrame } from '@/lib/voiceTurnContext';

/**
 * The voice server will not evaluate a turn without these fields, and we never
 * sent them: 11 failures / 0 successes on the VM on 7 Aug, every one of them
 * "turn_id is required for voice interactions", raised inside the voice server
 * before the tutor backend was ever called.
 */
describe('the voice server gets a turn it can actually evaluate', () => {
  it('carries the turn id', () => {
    expect(turnContextFrame('TURN-1', 'TUTOR-0')).toEqual({
      type: 'turn_context',
      turn_id: 'TURN-1',
      previous_tutor_turn_id: 'TUTOR-0',
      transcript_final: true,
    });
  });

  it('marks the transcript final — the server requires exactly true', () => {
    expect(turnContextFrame('TURN-1', null)?.transcript_final).toBe(true);
  });

  it('carries a null previous turn on the first turn of a session', () => {
    // Null is legal here (previous_tutor_turn_id is optional); only turn_id
    // itself is required.
    expect(turnContextFrame('TURN-1', null)?.previous_tutor_turn_id).toBeNull();
  });

  it('sends nothing at all rather than a null turn id', () => {
    // A frame with turn_id: null is exactly what the server rejects, so it is
    // worse than silence — it burns a turn and logs an error.
    expect(turnContextFrame(null, 'TUTOR-0')).toBeNull();
  });
});
