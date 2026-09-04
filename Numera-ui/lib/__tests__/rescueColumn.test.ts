/**
 * Rescue ink stays inside its column.
 *
 * Seen live on 4 Sep at 1200×692: an authored step was drawn as one unbounded
 * line from x=667px to x=1137px, while the support lane — which holds the
 * rescue panel itself — starts at x=912px. So the tutor's own writing ran under
 * the card describing it and was clipped mid-word.
 *
 * The file's own note predicted it: "a genuinely tight column, and long
 * authored steps will run toward the cards; that is worth watching."
 */

import { describe, it, expect } from 'vitest';
import { rescueSlot, RESCUE_WRAP_WIDTH, actionMarks } from '@/lib/tutorCanvasActions';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

/** The measured left edge of the support lane, as a fraction of canvas width. */
const LANE_LEFT = 0.70;

/** `rescueSlot` returns the target union; every rescue slot is a positioned one. */
const slotAt = (stepIndex: number) => {
  const target = rescueSlot(stepIndex);
  if (target.kind !== 'rescue-slot') throw new Error('rescueSlot returned a non-slot target');
  return target.at;
};

const action = (over: Partial<TutorCanvasAction> = {}): TutorCanvasAction => ({
  action_id: 'A1',
  type: 'TUTOR_SOLVED_STEP',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: 'TUTOR_ANCHOR:RESCUE:R1:STEP:1',
  confirmed_component_id: null,
  text: 'Verification step 1: subtract 6 from both sides.',
  source_id: 'TS-1',
  answer_reveal_allowed: false,
  rescue_id: 'R1',
  step_index: 1,
  total_steps: 3,
  presentation_mode: 'TUTOR_SOLVED',
  return_target_object_id: null,
  ...over,
} as TutorCanvasAction);

describe('a rescue step on the canvas', () => {
  it('is given a wrap width rather than running as one line', () => {
    const [mark] = actionMarks(action(), rescueSlot(1));
    expect(mark.wrapWidth).toBe(RESCUE_WRAP_WIDTH);
  });

  it('cannot reach the support lane, however long the sentence is', () => {
    const long = action({
      text: 'Because both sides must stay balanced, subtract six from the left and '
        + 'the right at the same time, which leaves three x on its own.',
    });
    const [mark] = actionMarks(long, rescueSlot(1));
    const rightEdge = (mark.x ?? 0) + (mark.wrapWidth ?? 0);
    // The bound is on the BOX, so it holds for any text — which is the point.
    // A width that merely fitted today's sample would fail on the next one.
    expect(rightEdge).toBeLessThanOrEqual(LANE_LEFT);
  });

  it('leaves room between rows for a wrapped step', () => {
    // Three lines at size 18 and line-height 1.25 is ~67px; the gap has to
    // clear that, or step 2 is drawn through step 1.
    const canvasHeight = 692;
    const gap = (slotAt(2).y - slotAt(1).y) * canvasHeight;
    expect(gap).toBeGreaterThan(18 * 1.25 * 3);
  });

  it('still stacks by authored index, not by occupancy', () => {
    // Unchanged by this work, and worth holding: step 3 belongs on row 3 even
    // when a reconnect lost rows 1 and 2.
    expect(slotAt(3).y).toBeGreaterThan(slotAt(1).y);
  });
});
