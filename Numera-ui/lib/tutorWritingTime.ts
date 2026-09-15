/**
 * How long the tutor's handwriting actually takes.
 *
 * Issue #304 (Sanya, 14 Sep 2026): "Tutor writes on canvas to confirm what the
 * student said but with out completing immediately moves to next question
 * /sections."
 *
 * Two pieces of this app had opinions about that duration and they disagreed.
 *
 *   `useTutorReveal` writes a text mark over `max(700, chars × 95)ms`, plus a
 *   260ms breath between marks. A one-line confirmation — "Start: n, Gain: +5",
 *   eighteen characters — therefore takes about 1.7 SECONDS, and a two-mark
 *   confirmation the better part of four.
 *
 *   `revealBeforeClear` held the board for a flat `REVEAL_MS = 900` before
 *   letting the phase change land, on the reasoning that 900ms is "long enough
 *   to read a short annotation".
 *
 * Long enough to read one, but not long enough to WRITE one. The phase change
 * landed at 900ms, `applyBackendPhase` cleared the tutor layer, and the student
 * watched the tutor start writing the confirmation and get cut off mid-word on
 * the way to the next question. Exactly what #304 describes, and the reason it
 * reads as a backend "moves on too early" bug when it is ours.
 *
 * So the duration now has ONE definition, here, and both the animation and the
 * hold read it. The bug was two numbers for one fact; a shared constant is the
 * only fix that cannot drift back.
 */

import type { TutorElement } from '@/store/useNumeraStore';

/**
 * A person finishes a line, lifts, and repositions before the next one. 90ms
 * read as a machine moving on; this is closer to a breath.
 */
export const GAP_MS = 260;

/**
 * The longest the board is ever held for.
 *
 * The hold is now derived from content, and content arrives from a model. A
 * pathological batch — a dozen marks, or one very long line — would otherwise
 * freeze the lesson on a finished question for ten seconds or more, which is a
 * worse failure than the one being fixed: the student can see the writing has
 * stopped and has no way to move on. Past this point the remaining marks are
 * cut off, as they were before, but only in the case that was never going to
 * be watchable anyway.
 */
export const MAX_HOLD_MS = 6_000;

/**
 * Nobody writes two lines at exactly the same rate. Vary each mark by up to
 * ±12%, derived from its id so a given mark always writes the same way — a
 * random factor would make replays and reconnects visibly inconsistent, and
 * would also make the hold computed here disagree with the animation it is
 * meant to be waiting for.
 */
function tempoFor(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return 0.88 + (Math.abs(h) % 100) / 100 * 0.24; // 0.88 – 1.12
}

/**
 * How long a single mark takes to "write", scaled by how much there is to draw.
 * Paced for a calm, deliberate hand — slow enough to read as writing, not a pop.
 */
export function elementWritingMs(el: TutorElement): number {
  const base = (() => {
    switch (el.kind) {
      case 'text':      return Math.max(700, (el.text?.length ?? 0) * 95);
      case 'math':      return Math.max(750, (el.tex ?? el.text ?? '').length * 80);
      case 'line':      return 620;
      case 'arrow':     return 720;
      case 'ellipse':   return 1150;
      case 'rect':      return 1040;
      case 'freehand':  return Math.max(600, ((el.points?.length ?? 0) / 2) * 32);
      case 'highlight': return Math.max(480, ((el.points?.length ?? 0) / 2) * 24);
      default:          return 620;
    }
  })();
  return base * tempoFor(el.id);
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/**
 * How much writing is still owed on the marks currently on the board.
 *
 * `progress` is `useTutorReveal`'s map, 0→1 per element id. Three states, and
 * the difference between them is the whole point:
 *
 *   id absent      A mark just added and not yet picked up by the sequencer,
 *                  which runs from an effect AFTER the store write. This is
 *                  the case that matters — the confirmation being written
 *                  right now — and it counts in full.
 *   0 < p < 1      Mid-write. Counts for what is left of it.
 *   p >= 1         Finished. Owes nothing, so a board full of marks from
 *                  earlier turns does not hold the next question back.
 *
 * Reduced motion draws everything at once, so there is nothing to wait for.
 */
export function outstandingWritingMs(
  elements: readonly TutorElement[],
  progress: Readonly<Record<string, number>>,
  reducedMotion: boolean = prefersReducedMotion(),
): number {
  if (reducedMotion) return 0;
  let total = 0;
  let pending = 0;
  for (const el of elements) {
    const done = progress[el.id] ?? 0;
    if (done >= 1) continue;
    total += elementWritingMs(el) * (1 - done);
    pending += 1;
  }
  // One breath BETWEEN marks, so a single mark gets none. The sequencer pauses
  // after each completed mark before starting the next.
  if (pending > 1) total += GAP_MS * (pending - 1);
  return total;
}
