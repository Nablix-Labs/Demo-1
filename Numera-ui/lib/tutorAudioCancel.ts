/**
 * The voice server has abandoned the tutor reply it was streaming.
 *
 * Deepgram Flux detects the start of a student's speech (`StartOfTurn`), so the
 * server can now cancel a tutor turn the moment it is interrupted. It stops
 * sending audio and sends this frame; the browser still holds whatever already
 * arrived, so without a handler the student hears the tail of a sentence after
 * they have started talking over it (Aditya, 14 Aug 2026).
 *
 * The interesting part is not the silence, it is the TURN. On a barge-in the
 * tutor audio never reaches idle, so the `setOnIdle` handler that normally opens
 * the next student turn never runs — and the barged-in turn would then reach the
 * server with the previous turn's latch, which is the `turn_id is required for
 * voice interactions` failure all over again (see lib/voiceTurnContext).
 *
 * Whether to reopen depends on WHY the reply was cancelled, and the two reasons
 * want opposite handling: a barge-in needs a fresh turn, a reply superseded by a
 * typed answer must not get one, because the text path has already minted its
 * own via `beginSubmissionTurn`. So the server states it outright rather than
 * making us infer turn semantics from a reason string.
 */
export interface TutorAudioCancelFrame {
  /** `barge_in` | `superseded_by_text` today; the server may add more. */
  reason?: string | null;
  /** The server's own answer: does it expect the client to open a new turn? */
  expect_new_turn?: boolean | null;
}

/**
 * Should the student's turn be reopened after this cancellation?
 *
 * The flag decides it whenever the server sent one. The fallback on `reason`
 * exists for the case where it did not: defaulting to `false` would silently
 * restore the missing-turn-context bug this frame was added to avoid, and a
 * frame that reaches us without the flag is exactly the situation where we
 * cannot afford to guess wrong.
 */
export function reopensStudentTurn(frame: TutorAudioCancelFrame): boolean {
  if (typeof frame.expect_new_turn === 'boolean') return frame.expect_new_turn;
  return frame.reason === 'barge_in';
}
