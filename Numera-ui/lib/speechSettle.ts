/**
 * When has the student stopped talking long enough that the server has taken
 * the turn?
 *
 * The socket gives us no marker for this. Deepgram's UtteranceEnd is what makes
 * the server finalise a turn, and the server does not forward that event — it
 * just acts on it (streaming_server.py:385). What we DO see is
 * `transcript_final`, and that fires per Deepgram SEGMENT, not per turn
 * (line 373, gated on `is_final`). One spoken answer with a small pause in it
 * produces several.
 *
 * So "the student sent their answer" cannot be read off any single frame. Treat
 * the first final as the end of the turn and the UI closes the mic on someone
 * who is mid-sentence — the same premature split that makes "It is… 5" get
 * evaluated as two answers.
 *
 * Instead, mirror the server's own rule: the turn has settled once no new
 * speech has arrived for `utterance_end_ms`. Any partial or final restarts the
 * clock, so a student who resumes talking cancels it, exactly as resumed speech
 * cancels the server's finalisation.
 *
 * This is a DISPLAY signal derived from the server's timing, not a second
 * source of truth. If the voice server ever sends an explicit "processing"
 * status frame, delete this and use that — it would be exact where this is
 * inferred. That ask is on the voice-server owner.
 */

/**
 * Deepgram's `utterance_end_ms` as the voice server configures it — see the
 * derivation in lib/turnWatchdog.ts, which depends on the same number.
 */
export const UTTERANCE_END_MS = 1_500;

export class SpeechSettleTimer {
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly onSettled: () => void,
    private readonly windowMs: number = UTTERANCE_END_MS,
  ) {}

  /** True while we are waiting to see whether the student says more. */
  get pending(): boolean {
    return this.timer !== null;
  }

  /**
   * The student produced speech. Restarts the clock — more speech means the
   * turn has not settled, and any pending decision must be thrown away.
   */
  noteSpeech(): void {
    this.cancel();
    this.timer = setTimeout(() => {
      this.timer = null;
      this.onSettled();
    }, this.windowMs);
  }

  /** The turn resolved, failed, or the socket went away. */
  cancel(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
