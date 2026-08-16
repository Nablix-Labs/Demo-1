/**
 * A tutor turn the student abandoned, which the backend committed anyway.
 *
 * Cancelling a barged-in turn used to throw away the whole reply. That saved
 * nothing — the backend had already run the pipeline, two OpenAI calls, and
 * returned 200 with `state_version` bumped, three seconds after the voice server
 * stopped listening (Aditya, 15 Aug 2026, VM 11:08). What it discarded was the
 * one part the client needed: the `tutor_turn_id` the NEXT turn has to point at.
 *
 * The session died as a result. Turn 17 was rejected for reusing turn 16's id —
 * the barge-in gap our `tutor_audio_cancel` handler closes — and turn 18, with a
 * freshly minted id, was rejected as STALE_TURN, because `previous_tutor_turn_id`
 * was still pointing at turn 15. Both fixes are needed; neither alone recovers
 * the session.
 *
 * So the server now lets a suppressed turn finish and forwards its lineage in
 * this frame, with the tutor's text and audio dropped. Nothing here is rendered:
 * the student walked away from this answer deliberately, and putting it on
 * screen two seconds into their next sentence is the tutor talking over them.
 *
 * TIMING is the whole hazard. The frame describes the turn BEFORE the one now in
 * progress, and lands two to four seconds into it. So only the tutor pointer may
 * move — see `noteTutorLineage` in the store for what must not.
 */

export interface TutorTurnCommittedFrame {
  /** The tutor turn the next student turn must reference. */
  tutor_turn_id?: string | null;
  /** The student turn that was committed. Correlation and gate identity. */
  accepted_turn_id?: string | null;
  interaction_state_version?: number | null;
  /** `barge_in` today. Informational. */
  reason?: string | null;
  /** The abandoned transcript, for log correlation only. Never rendered. */
  transcript?: string | null;
}

/**
 * The lineage to adopt, or null when the frame carries none.
 *
 * Null rather than a blank pointer: `lastTutorTurnId` is what the next turn
 * sends as `previous_tutor_turn_id`, and the backend rejects a null one
 * outright. A frame that arrives without an id must therefore leave the pointer
 * where it is — an out-of-date pointer still describes a real turn, whereas an
 * erased one fails every turn after it.
 */
export function committedLineage(frame: TutorTurnCommittedFrame): string | null {
  const id = typeof frame.tutor_turn_id === 'string' ? frame.tutor_turn_id.trim() : '';
  return id || null;
}
