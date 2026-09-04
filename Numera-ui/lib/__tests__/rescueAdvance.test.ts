/**
 * "Next step" — one request, one new step, and a button that recovers.
 *
 * The two failures worth pinning are opposites. A latch that is too STICKY
 * leaves the student holding a dead button for the rest of the question; a
 * latch that is too loose lets a double-press send two advances, and the second
 * one is a step the student never read.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { advancePending, advanceFailed } from '@/lib/rescueMode';

const at = (rescueId: string, stepIndex: number) => ({ rescueId, stepIndex });

describe('while an advance is outstanding', () => {
  it('is not pending before anything is pressed', () => {
    expect(advancePending(null, at('R1', 1))).toBe(false);
  });

  it('is pending once step 2 has been asked for and step 1 is still showing', () => {
    // This is what disables the button, so it is what stops a double-press
    // becoming two requests.
    expect(advancePending({ rescueId: 'R1', step: 2 }, at('R1', 1))).toBe(true);
  });

  it('stops being pending the moment the step arrives', () => {
    expect(advancePending({ rescueId: 'R1', step: 2 }, at('R1', 2))).toBe(false);
  });

  it('stops being pending if the backend jumps further ahead', () => {
    // Asked for 2, given 3. The student has a step in front of them, so the
    // button must work again — waiting for exactly 2 would hang forever.
    expect(advancePending({ rescueId: 'R1', step: 2 }, at('R1', 3))).toBe(false);
  });

  it('does not carry into a rescue that superseded this one', () => {
    // Press Next on step 3 of A; A is replaced by B starting at step 1. Keyed
    // on the step number alone, B opened with its button already disabled and
    // nothing that could ever re-enable it.
    expect(advancePending({ rescueId: 'R1', step: 4 }, at('R2', 1))).toBe(false);
  });
});

describe('when an advance did not land', () => {
  it('reports nothing when there was no failure', () => {
    expect(advanceFailed(null, at('R1', 1))).toBe(false);
  });

  it('reports on the step the student actually pressed', () => {
    expect(advanceFailed({ rescueId: 'R1', step: 1 }, at('R1', 1))).toBe(true);
  });

  it('does not follow the student onto the step that DID arrive', () => {
    // Held as a bare boolean it did: step 2 rendered with "couldn't ask for the
    // next step" underneath it — a failure notice attached to a success.
    expect(advanceFailed({ rescueId: 'R1', step: 1 }, at('R1', 2))).toBe(false);
  });

  it('does not follow into the next rescue', () => {
    expect(advanceFailed({ rescueId: 'R1', step: 1 }, at('R2', 1))).toBe(false);
  });
});

describe('the advance frame itself', () => {
  beforeEach(async () => {
    const { registerRescueTransport } = await import('@/lib/rescueEvents');
    registerRescueTransport(null);
  });

  it('sends exactly one frame per press, carrying the step being looked at', async () => {
    const { registerRescueTransport, emitRescueAdvance } = await import('@/lib/rescueEvents');
    const sent: unknown[] = [];
    registerRescueTransport((event) => { sent.push(event); return true; });

    emitRescueAdvance({
      event_type: 'RESCUE_STEP_ADVANCE',
      session_id: 'S1', question_id: 'Q-1', rescue_id: 'R1',
      current_step_index: 2, trigger: 'UI_NEXT_STEP',
    });

    expect(sent).toHaveLength(1);
    // Never pre-incremented: the backend rejects an index that does not match
    // the one it has persisted, which is what makes a replayed frame a no-op
    // rather than a skipped step.
    expect((sent[0] as { current_step_index: number }).current_step_index).toBe(2);
  });

  it('reports a press that could not be delivered, so the button can recover', async () => {
    const { registerRescueTransport, emitRescueAdvance } = await import('@/lib/rescueEvents');
    registerRescueTransport(() => false);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(emitRescueAdvance({
      event_type: 'RESCUE_STEP_ADVANCE',
      session_id: 'S1', question_id: 'Q-1', rescue_id: 'R1',
      current_step_index: 1, trigger: 'UI_NEXT_STEP',
    })).toBe(false);
    warn.mockRestore();
  });
});
