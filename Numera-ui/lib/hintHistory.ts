/**
 * The support a student has already been given on the question in front of them.
 *
 * Issue #312 (Sanya, 14 Sep 2026): "I clicked earlier help ( Hint) it is showing
 * a third hint ( i was at visual cue step , so previosu help are hint 1 , hint 2
 * ) but it gave me a third hint , and hint 1 , 2 were not visisble".
 *
 * The screen held one `hintText` and rendered it in one sticky note, so each new
 * rung of the support ladder overwrote the one before it. By the third press the
 * student could see only the third hint — which is the one written on the
 * assumption that they have just read the first two. Support that builds on
 * itself has to stay on the page, or each rung reads as a non-sequitur and the
 * student has no way back to what they were told thirty seconds ago.
 *
 * Kept per QUESTION, not per session: the ladder resets when the question does,
 * and a hint about the previous question sitting beside a new one is worse than
 * no hint at all.
 */

/**
 * How many rungs stay on screen.
 *
 * The ladder is hint → visual cue → scaffold, so three is the whole of it; the
 * cap exists for the case where the backend replays a rung and for authored
 * content nobody has counted. Beyond this the notes would cover the canvas the
 * student is meant to be working on, which is the opposite of help.
 */
export const MAX_VISIBLE_HINTS = 4;

/**
 * Add a newly served hint, keeping the ones already showing.
 *
 * Three things it refuses, all of which produce a note that says nothing:
 *
 *  - empty or blank text. A rung the backend served with no words is not
 *    something to render an empty card for.
 *  - a repeat of what is already the latest note. Pressing Help when the
 *    backend has nothing new to authorise replays the current rung, and
 *    stacking it twice makes the tutor look like it is stuttering.
 *  - anything past the cap, oldest first.
 *
 * A repeat that is NOT the latest is kept: coming back to the first hint after
 * a cue is the tutor deliberately returning to it, and dropping it would leave
 * the sequence unreadable.
 */
export function appendHint(hints: readonly string[], served: string | null | undefined): string[] {
  const text = served?.trim();
  if (!text) return [...hints];
  if (hints.length > 0 && hints[hints.length - 1] === text) return [...hints];
  return [...hints, text].slice(-MAX_VISIBLE_HINTS);
}

/**
 * The label beside each note — "Hint 1", "Hint 2".
 *
 * Numbered from the top of what is SHOWING rather than from the top of the
 * ladder. Once the cap has dropped a note, a label counting from the real rung
 * number would read "Hint 2, Hint 3, Hint 4" with no hint 1 anywhere, and the
 * student would go looking for something that is not there.
 */
export function hintLabel(index: number, total: number): string {
  return total > 1 ? `Hint ${index + 1}` : 'Gentle hint';
}
