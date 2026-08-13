/**
 * What to call the amber note on the canvas.
 *
 * Two reports pull in opposite directions and both are right:
 *
 *   Manjusha, 10 Aug — hints were being titled "Visual cue".
 *   Sanya, 13 Aug    — real visual cues are being titled "Hint".
 *
 * The old rule asked the wrong question. It labelled by whether the CLIENT held
 * a hardcoded card, and VISUAL_CUE_CARDS covers five linear-equation demo types
 * — so every authored Topic 1 cue (VC-T01-…) fell through to "Hint", which is
 * Sanya's bug, while the tutor's own guidance text also had no card and
 * correctly read "Hint", which is Manjusha's fix.
 *
 * Label by what the BACKEND served instead. `cue_id` is the discriminator:
 * present means the Student Model served an authored cue from the catalogue,
 * absent means the note is the tutor's own words. `cue_type` cannot do this job
 * — it is null on every real cue.
 */

export function cueLabel({
  cardTitle,
  cueId,
}: {
  /** Title of the client-side card for this cue_type, when one matches. */
  cardTitle: string | null | undefined;
  /** The backend's cue_id, trimmed to null when absent or blank. */
  cueId: string | null | undefined;
}): string {
  if (cardTitle) return cardTitle;
  return cueId ? 'Visual cue' : 'Hint';
}
