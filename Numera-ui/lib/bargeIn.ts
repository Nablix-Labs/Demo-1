/**
 * The student started talking while the tutor was still speaking.
 *
 * Two facts are needed and they live on opposite sides of the socket (Aditya,
 * 17 Aug 2026):
 *
 *   the student has started speaking   only the SERVER knows — Flux StartOfTurn,
 *                                      derived from the audio
 *   audio is currently playing         only the CLIENT knows — the server's view
 *                                      ends when it finishes SENDING, which is
 *                                      under a second ("5 chunks in 732ms")
 *                                      while the browser then plays for five or
 *                                      ten more
 *
 * For nearly all of the time the student can actually hear the tutor, the server
 * considers the turn finished. Neither side can act alone.
 *
 * Aditya tried it server-side first and it fired on every turn: a normal reply
 * is also a StartOfTurn, and nothing ever told the server that playback had
 * ended, so it could not tell an interruption from an answer. The missing half
 * was ours. Which is the rule here — whoever observes the fact reports it,
 * whoever owns the resource decides — and the audio element is ours.
 *
 * We do not need a new message to learn the server's half. The mic is not gated
 * on tutor speech (app/page.tsx sets capture from `!micMuted` alone), so
 * `transcript_partial` already arrives DURING playback, and a partial while
 * audio is playing is the student talking over the tutor.
 *
 * The one thing that makes this safe rather than a repeat of the server-side
 * mistake is that `aiSpeaking` is driven by playback genuinely advancing (see
 * lib/tts's mouth timer, which watches `currentTime`), not by intent to play.
 * A turn where the student answers after the tutor finished cannot satisfy it,
 * which is precisely the discriminator the server lacked.
 */

export interface BargeInSignal {
  /** Tutor audio genuinely playing right now. */
  audioPlaying: boolean;
  /** The partial transcript that just arrived. */
  text: string | null | undefined;
}

/**
 * Should this partial stop the tutor?
 *
 * Empty partials do not count. Deepgram emits them around the edges of speech,
 * and stopping the tutor because the recogniser twitched would cut the tutor off
 * mid-sentence for a student who never spoke — the failure mode this is supposed
 * to prevent, aimed the other way.
 *
 * Capture runs with `echoCancellation: true`, so the tutor's own voice coming
 * back through the microphone is suppressed before it ever reaches a transcript.
 * Without that, this rule would let the tutor interrupt itself.
 */
export function interruptsTutor({ audioPlaying, text }: BargeInSignal): boolean {
  if (!audioPlaying) return false;
  return Boolean(text?.trim());
}
