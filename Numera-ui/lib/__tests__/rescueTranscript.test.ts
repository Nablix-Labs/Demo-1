/**
 * One child-facing tutor message on the turn a rescue opens.
 *
 * The rule is deliberately narrow — it applies to rescue turns, not to every
 * turn everywhere — so the tests that matter are the ones that pin the EDGE:
 * an ordinary turn must keep its hint, and a turn whose rescue actions cannot
 * render is an ordinary turn.
 */

import { describe, it, expect } from 'vitest';
import { opensRescue } from '@/lib/rescueTranscript';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

const action = (over: Partial<TutorCanvasAction> = {}): TutorCanvasAction => ({
  action_id: 'TURN-1:1:TUTOR_SOLVED_STEP:R1:1',
  type: 'TUTOR_SOLVED_STEP',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: 'TUTOR_ANCHOR:RESCUE:R1:STEP:1',
  confirmed_component_id: null,
  text: 'Subtract 6 from both sides.',
  source_id: 'TS-1',
  answer_reveal_allowed: false,
  rescue_id: 'R1',
  step_index: 1,
  total_steps: 3,
  presentation_mode: 'TUTOR_SOLVED',
  return_target_object_id: null,
  ...over,
} as TutorCanvasAction);

describe('recognising a rescue turn', () => {
  it('is not one when the turn carried no actions at all', () => {
    expect(opensRescue({})).toBe(false);
    expect(opensRescue({ tutor_canvas_actions: [] })).toBe(false);
    expect(opensRescue(null)).toBe(false);
  });

  it('is one when a rescue step will render', () => {
    expect(opensRescue({ tutor_canvas_actions: [action()] })).toBe(true);
  });

  it('is one for a parallel example too, not just tutor-solved', () => {
    expect(opensRescue({
      tutor_canvas_actions: [action({ type: 'SHOW_PARALLEL', presentation_mode: 'PARALLEL' })],
    })).toBe(true);
  });

  it('is NOT one when the rescue action cannot render', () => {
    // No rescue_id: nothing can acknowledge, advance or supersede it, so the
    // store records nothing and no panel opens. Treating this as a rescue turn
    // would suppress the hint and leave the student with neither the support
    // they were given nor the walkthrough that was meant to replace it.
    expect(opensRescue({ tutor_canvas_actions: [action({ rescue_id: null })] })).toBe(false);
  });

  it('is NOT one for an ordinary annotation', () => {
    expect(opensRescue({
      tutor_canvas_actions: [action({
        type: 'INSERT_LABEL', rescue_id: null, step_index: null, total_steps: null,
        presentation_mode: null,
      })],
    })).toBe(false);
  });

  it('is one when a rescue step arrives alongside ordinary annotations', () => {
    expect(opensRescue({
      tutor_canvas_actions: [
        action({ action_id: 'A0', type: 'INSERT_LABEL', rescue_id: null, step_index: null }),
        action(),
      ],
    })).toBe(true);
  });
});
