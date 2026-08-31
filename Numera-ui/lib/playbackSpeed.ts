/**
 * Playback speed for the orientation video.
 *
 * Manjusha, 30 Aug 2026: "can you control the speed of the orientation video
 * from the front end". Chrome does hide a speed menu inside its native video
 * controls, but it is two levels deep in an overflow menu, it is not there on
 * every browser, and a student watching a concept explanation should not have
 * to go looking. So the rates are surfaced as their own control.
 *
 * The chosen rate is remembered for the session because the orientation screen
 * REMOUNTS the player: "Watch again" replays by bumping a React key, and a
 * bundle can carry several videos. Without this, a student who picked 1.5×
 * would be dropped back to 1× by their own replay button and again by the next
 * video — which reads as the control not working.
 *
 * Deliberately module-level rather than persisted: it is a preference about
 * this sitting, not about this student, and nothing else in the app writes a
 * viewing preference to the student's device.
 */

/** The offered rates. 2× is the ceiling: speech stops being followable past it. */
export const PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 2] as const;

export type PlaybackRate = (typeof PLAYBACK_RATES)[number];

export const DEFAULT_RATE: PlaybackRate = 1;

let sessionRate: PlaybackRate = DEFAULT_RATE;

/** The rate to open the next player at. */
export function currentRate(): PlaybackRate {
  return sessionRate;
}

/**
 * Remember a rate for the rest of the session.
 *
 * Guarded rather than trusting the caller: an unknown rate reaching the video
 * element would be applied by the browser (playbackRate takes any positive
 * number), so a bad value would silently leave the student on a speed the
 * control cannot show as selected or undo.
 */
export function rememberRate(rate: number): PlaybackRate {
  const known = PLAYBACK_RATES.find((r) => r === rate);
  sessionRate = known ?? DEFAULT_RATE;
  return sessionRate;
}

/** Test seam: forget the session's choice. */
export function resetRate(): void {
  sessionRate = DEFAULT_RATE;
}

/** "1×", "1.5×" — no trailing zeros, because "1.50×" reads as a measurement. */
export function rateLabel(rate: number): string {
  return `${rate}×`;
}
