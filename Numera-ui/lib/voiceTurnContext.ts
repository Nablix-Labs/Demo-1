/**
 * The turn identity the voice server needs before it can evaluate a turn.
 *
 * The server refuses to call the tutor backend without a `turn_id`
 * (streaming_server.py:139) and without `transcript_final === true` (line 141).
 * It takes all three fields off ANY text frame the client sends
 * (streaming_server.py:437-441 — the latch runs before the msg_type dispatch,
 * so the type itself is not what carries them), and clears them again after
 * each turn is processed (lines 419-421, 551-553).
 *
 * We never sent them. `setTutorTurn`/`turn_id` existed only on the REST path,
 * so on the server transport every single voice turn died inside the voice
 * server before the backend was ever contacted — 11 failures, 0 successes on
 * the VM on 7 Aug, all reading "turn_id is required for voice interactions".
 * That surfaced to the student as "Tutor unavailable", which is why it was
 * mistaken first for a frontend timeout and then for a backend fault.
 *
 * Because the server clears the latch per turn, this must be sent once at the
 * start of EVERY student turn, not once per connection.
 */
export interface VoiceTurnContextFrame {
  type: 'turn_context';
  turn_id: string;
  previous_tutor_turn_id: string | null;
  /**
   * The server requires exactly `true`. We only ever submit a turn the server
   * itself finalised via UtteranceEnd, so from our side it is always final.
   */
  transcript_final: true;
}

/**
 * Build the frame, or null when there is no turn to describe yet — sending
 * `turn_id: null` is what the backend rejects, so not sending is better.
 */
export function turnContextFrame(
  turnId: string | null,
  previousTutorTurnId: string | null,
): VoiceTurnContextFrame | null {
  if (!turnId) return null;
  return {
    type: 'turn_context',
    turn_id: turnId,
    previous_tutor_turn_id: previousTutorTurnId,
    transcript_final: true,
  };
}
