/**
 * Static visual-cue card library.
 *
 * When the AI Engine detects a student mistake it sends a `visual_cue` object
 * (see the VisualCue contract in lib/api.ts) with a `cue_type`. The frontend maps
 * that type to one of these cards and renders it — the backend never sends card
 * UI, only the type + instructional intent. Content is deliberately reusable
 * across questions; the backend's `description` is layered on as extra guidance.
 *
 * For the demo these are static (per Sanya's handoff). Later they come from
 * Aditya's RAG — swap resolveCueCard's source then, the render stays the same.
 */

export type CueType =
  | 'EQUATION_BLOCK'
  | 'INVERSE_OPERATION'
  | 'ARITHMETIC_CHECK'
  | 'ISOLATE_VARIABLE'
  | 'MULTI_STEP_EQUATION';

export interface VisualCueCard {
  title: string;
  example: string;
  steps: string[];
  caption: string;
}

export const VISUAL_CUE_CARDS: Record<CueType, VisualCueCard> = {
  EQUATION_BLOCK: {
    title: 'Equation balance',
    example: 'x + 4 = 9',
    steps: [
      'Keep both sides equal.',
      'Use the opposite operation on both sides.',
      'Do not change only one side.',
    ],
    caption: 'Whatever you do to one side, do the same to the other side.',
  },
  INVERSE_OPERATION: {
    title: 'Use the opposite operation',
    example: 'x + 4 = 9  →  subtract 4 from both sides',
    steps: [
      'Find the number attached to x.',
      'Use the opposite operation.',
      'Apply it to both sides.',
    ],
    caption: 'To undo addition, subtract. To undo subtraction, add.',
  },
  ARITHMETIC_CHECK: {
    title: 'Check the arithmetic',
    example: '9 − 4 = ?',
    steps: [
      'Recalculate the number step.',
      'Check the operation sign.',
      'Then write the value of x.',
    ],
    caption: 'The equation step may be right, but the number calculation needs checking.',
  },
  ISOLATE_VARIABLE: {
    title: 'Isolate x',
    example: 'x + 4 = 9  →  x = 9 − 4',
    steps: [
      'Move everything except x to the other side.',
      'Use inverse operations.',
      'Leave x by itself.',
    ],
    caption: 'The goal is to get x alone.',
  },
  MULTI_STEP_EQUATION: {
    title: 'Solve one step at a time',
    example: '2x + 5 = 13',
    steps: [
      'First remove the constant.',
      'Then divide by the coefficient.',
      'Check your final answer.',
    ],
    caption: 'Do one operation at a time in the correct order.',
  },
};

/** Cards shown when the AI Engine asks for a cue but sends no (or an unknown)
 *  cue_type — e.g. a session-start `show_visual_cue` or the dev toggle. */

/** Resolve a backend cue_type to a card, always returning something renderable. */
/**
 * The card for a backend cue_type, or null when we don't have one.
 *
 * Returning null matters. This used to fall back to a DEFAULT_CUE card, so an
 * unknown or missing cue_type rendered a fixed worked example about a
 * completely different equation — invented content, presented to the student as
 * if the tutor had chosen it. That is what "it shows the old visual cue" looks
 * like from the outside (Sanya, 2026-07-29), and the Phase 2 handoff §9 forbids
 * it outright: never derive support content from hardcoded frontend examples
 * when the backend has supplied authored content.
 *
 * With null, VisualCue shows the backend's own description instead, and shows
 * nothing at all when there is neither.
 */
export function resolveCueCard(cueType: string | null | undefined): VisualCueCard | null {
  if (cueType && cueType in VISUAL_CUE_CARDS) {
    return VISUAL_CUE_CARDS[cueType as CueType];
  }
  return null;
}
