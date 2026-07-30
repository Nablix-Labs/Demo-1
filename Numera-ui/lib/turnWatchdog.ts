/**
 * Rescue for a student turn the voice server never finished.
 *
 * On the 'server' transport the server decides when the student has stopped
 * talking, and it has exactly one way to decide: Deepgram's UtteranceEnd, which
 * fires after `utterance_end_ms=1500` of silence. There is no other trigger —
 * we have never sent the `stop` control message the server also supports.
 *
 * So when that one event doesn't arrive (noisy room, a dropped Deepgram frame,
 * a reconnect that discarded the utterance) the turn simply never completes.
 * The student has spoken, sees their words transcribed, and then waits forever
 * with no way to push the answer through.
 *
 * This watchdog is the way out. It arms when the student's speech is
 * transcribed and disarms the moment the tutor replies. If it ever expires, the
 * turn is genuinely stuck and we send `stop` to force the server to finalise.
 *
 * WHY THE WINDOW IS AS LONG AS IT IS — this is the whole safety argument, so
 * don't shorten it without re-reading it:
 *
 * The server's `stop` handler cancels its Deepgram receiver task after 10s
 * (streaming_server.py:503). That task is what runs the tutor turn when
 * UtteranceEnd DID fire. So a `stop` sent while a reply is still being produced
 * can cancel it mid-flight, leaving the student with audio chunks and no
 * `tutor_audio_end` — a response that currently works, broken by the rescue.
 *
 * The window must therefore outlast the slowest reply the server can produce:
 *
 *     1.5s   UtteranceEnd silence threshold
 *  + 15.0s   the tutor HTTP call's timeout (streaming_server.py:107)
 *  = 16.5s   after which the server has sent either `tutor_response` or `error`
 *
 * Both of those disarm us. 20s leaves 3.5s of margin, so by the time we fire,
 * nothing can still be in flight and the cancel is harmless.
 *
 * This is a rescue, not a turn-taking mechanism. In the normal case UtteranceEnd
 * fires, the tutor replies, and this never runs.
 */

/** See the derivation above before changing this. */
export const TURN_RESCUE_MS = 20_000;

export class TurnWatchdog {
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly onStuck: () => void,
    private readonly windowMs: number = TURN_RESCUE_MS,
  ) {}

  /** True while a student turn is awaiting a reply. */
  get armed(): boolean {
    return this.timer !== null;
  }

  /**
   * The student's speech was transcribed. Arms the rescue, restarting the clock
   * — each new segment means they are still talking, so the wait starts over.
   */
  noteStudentSpeech(): void {
    this.disarm();
    this.timer = setTimeout(() => {
      this.timer = null;
      this.onStuck();
    }, this.windowMs);
  }

  /** The tutor replied (or the server reported a failure). Nothing is stuck. */
  noteTurnResolved(): void {
    this.disarm();
  }

  /** The socket is going away; the rescue must not outlive it. */
  dispose(): void {
    this.disarm();
  }

  private disarm(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
