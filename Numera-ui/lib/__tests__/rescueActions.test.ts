/**
 * The rescue presentation's safety rules, tested at the level that matters:
 * what can reach a student's screen.
 *
 * The reveal cases are the point. Everything else here is bookkeeping; those
 * decide whether a student who is stuck gets shown the answer on a step where
 * nobody authorised it.
 */

import { describe, it, expect } from 'vitest';
import {
  rescueAnchorId, parseRescueAnchor, isRescueAction,
  answerRevealPermitted, rescueStep, isFinalStep, mergeStep, writesToStudentCanvas,
} from '@/lib/rescueActions';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

const SOLVED_FINAL: TutorCanvasAction = {
  action_id: 'TURN-123:1:TUTOR_SOLVED_STEP:RESCUE-T01-003-02:3',
  type: 'TUTOR_SOLVED_STEP',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: 'TUTOR_ANCHOR:RESCUE:RESCUE-T01-003-02:STEP:3',
  confirmed_component_id: null,
  text: 'Combine the starting value and the gain: s + 6.',
  source_id: 'TS-T01-003-01',
  answer_reveal_allowed: true,
  rescue_id: 'RESCUE-T01-003-02',
  step_index: 3,
  total_steps: 3,
  presentation_mode: 'TUTOR_SOLVED',
  return_target_object_id: 'TUTOR_ANCHOR:WRITE_RULE:Q-T01-003',
};

const PARALLEL_STEP1: TutorCanvasAction = {
  action_id: 'TURN-123:1:SHOW_PARALLEL:RESCUE-T01-003-01:1',
  type: 'SHOW_PARALLEL',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: 'TUTOR_ANCHOR:RESCUE:RESCUE-T01-003-01:STEP:1',
  confirmed_component_id: null,
  text: 'Start with p, then add 3.',
  source_id: 'PE-T01-003-01',
  answer_reveal_allowed: false,
  rescue_id: 'RESCUE-T01-003-01',
  step_index: 1,
  total_steps: 3,
  presentation_mode: 'PARALLEL',
  return_target_object_id: 'TUTOR_ANCHOR:ORIGINAL:Q-T01-003',
};

describe('rescue anchors', () => {
  it('round-trips', () => {
    const id = rescueAnchorId('RESCUE-T01-003-01', 2);
    expect(id).toBe('TUTOR_ANCHOR:RESCUE:RESCUE-T01-003-01:STEP:2');
    expect(parseRescueAnchor(id)).toEqual({ rescueId: 'RESCUE-T01-003-01', stepIndex: 2 });
  });

  it('is not confused with the other TUTOR_ANCHOR shapes', () => {
    expect(parseRescueAnchor('TUTOR_ANCHOR:WRITE_RULE:1')).toBeNull();
    expect(parseRescueAnchor('TUTOR_ANCHOR:CONFIRMED:Q-T01-003:1')).toBeNull();
    expect(parseRescueAnchor('TUTOR_ANCHOR:ORIGINAL:Q-T01-003')).toBeNull();
  });

  it('refuses a non-positive step', () => {
    expect(parseRescueAnchor('TUTOR_ANCHOR:RESCUE:R:STEP:0')).toBeNull();
  });
});

describe('answer reveal', () => {
  it('permits the authored final tutor-solved step', () => {
    expect(answerRevealPermitted(SOLVED_FINAL)).toBe(true);
  });

  it('refuses when the flag is absent', () => {
    expect(answerRevealPermitted({ ...SOLVED_FINAL, answer_reveal_allowed: false })).toBe(false);
  });

  // The four drift cases. Each is a payload that ASKS to reveal, on a step
  // where the handoff's conditions do not hold — which is exactly the shape a
  // renamed enum or an off-by-one upstream would produce.
  it('refuses a parallel example, whatever the flag says', () => {
    expect(answerRevealPermitted({
      ...PARALLEL_STEP1, answer_reveal_allowed: true, step_index: 3,
    })).toBe(false);
  });

  it('refuses a non-final step', () => {
    expect(answerRevealPermitted({ ...SOLVED_FINAL, step_index: 2 })).toBe(false);
  });

  it('refuses when the mode contradicts the type', () => {
    expect(answerRevealPermitted({ ...SOLVED_FINAL, presentation_mode: 'PARALLEL' })).toBe(false);
  });

  it('refuses when the step numbers are missing', () => {
    expect(answerRevealPermitted({
      ...SOLVED_FINAL, step_index: null, total_steps: null,
    })).toBe(false);
  });
});

describe('rescueStep', () => {
  it('normalises a parallel step', () => {
    expect(rescueStep(PARALLEL_STEP1)).toEqual({
      actionId: PARALLEL_STEP1.action_id,
      rescueId: 'RESCUE-T01-003-01',
      mode: 'PARALLEL',
      stepIndex: 1,
      totalSteps: 3,
      text: 'Start with p, then add 3.',
      anchorId: 'TUTOR_ANCHOR:RESCUE:RESCUE-T01-003-01:STEP:1',
      returnTargetObjectId: 'TUTOR_ANCHOR:ORIGINAL:Q-T01-003',
      answerReveal: false,
      sourceId: 'PE-T01-003-01',
    });
  });

  it('is null for a non-rescue action', () => {
    expect(rescueStep({ ...PARALLEL_STEP1, type: 'FOCUS' })).toBeNull();
  });

  // Every one of these would render text that no later event could refer to.
  it('is null when the identifying fields are missing', () => {
    expect(rescueStep({ ...PARALLEL_STEP1, rescue_id: null })).toBeNull();
    expect(rescueStep({ ...PARALLEL_STEP1, text: '   ' })).toBeNull();
    expect(rescueStep({ ...PARALLEL_STEP1, step_index: null })).toBeNull();
  });

  it('is null when the mode contradicts the type', () => {
    expect(rescueStep({ ...PARALLEL_STEP1, presentation_mode: 'TUTOR_SOLVED' })).toBeNull();
  });

  it('takes the mode from the type when the backend omits it', () => {
    const step = rescueStep({ ...PARALLEL_STEP1, presentation_mode: null });
    expect(step?.mode).toBe('PARALLEL');
  });

  it('reports an unusable total as unknown, and unknown is NOT final', () => {
    // This used to default to the step index, which made "I don't know how many
    // steps there are" render as "this is the last one": the panel showed
    // "Step 2 of 2" and offered Return instead of Next, cutting the student off
    // from the rest of a walkthrough while claiming it had finished. Sanya nulls
    // fields without notice, so this is the likely real-world shape.
    for (const total of [0, null, undefined]) {
      const step = rescueStep({ ...PARALLEL_STEP1, step_index: 2, total_steps: total });
      expect(step?.totalSteps).toBeNull();
      expect(isFinalStep(step!)).toBe(false);
    }
  });

  it('is still final when the backend does say so', () => {
    const step = rescueStep({ ...PARALLEL_STEP1, step_index: 3, total_steps: 3 });
    expect(isFinalStep(step!)).toBe(true);
  });
});

describe('mergeStep', () => {
  const step = (i: number) => rescueStep({
    ...PARALLEL_STEP1,
    action_id: `A${i}`,
    step_index: i,
    target_object_id: rescueAnchorId('RESCUE-T01-003-01', i),
  })!;

  it('appends in step order regardless of arrival order', () => {
    const merged = mergeStep(mergeStep([], step(2)), step(1));
    expect(merged.map((s) => s.stepIndex)).toEqual([1, 2]);
  });

  it('replaces a re-delivered step rather than duplicating it', () => {
    const merged = mergeStep(mergeStep([], step(1)), step(1));
    expect(merged).toHaveLength(1);
  });

  it('starts over when a different rescue arrives', () => {
    const other = rescueStep({
      ...PARALLEL_STEP1, action_id: 'B1', rescue_id: 'RESCUE-OTHER',
    })!;
    const merged = mergeStep(mergeStep([], step(1)), other);
    expect(merged.map((s) => s.rescueId)).toEqual(['RESCUE-OTHER']);
  });
});

describe('which rescue steps reach the student\'s canvas', () => {
  // Sanya's rescue handoff, item 3, draws the line: tutor-solved is "add each
  // authorised worked step without overwriting the child's writing" — the tutor
  // working through the student's OWN problem — while a parallel example gets
  // "a split view between the original question and similar example", because
  // it is a different problem entirely.
  //
  // Nothing enforced that, so a parallel example was written across the page
  // the student was answering on: `2x + 4 = 10` sprawled over the working area
  // for `3x + 6 = 18`. Found on 31 Aug by running the presentation with the
  // flag on, which no test had done.
  const action = (over: Record<string, unknown> = {}) => ({
    action_id: 'A1', type: 'TUTOR_SOLVED_STEP', target_kind: 'TUTOR_ANCHOR',
    target_object_id: 'TUTOR_ANCHOR:RESCUE:R1:STEP:1',
    confirmed_component_id: null, text: 'Take 6 from both sides.',
    source_id: 'R1', answer_reveal_allowed: false,
    rescue_id: 'R1', step_index: 1, total_steps: 3,
    presentation_mode: 'TUTOR_SOLVED', return_target_object_id: null,
    ...over,
  }) as unknown as Parameters<typeof writesToStudentCanvas>[0];

  it('writes a tutor-solved step onto the canvas', () => {
    expect(writesToStudentCanvas(action())).toBe(true);
  });

  it('keeps a parallel example OFF the canvas', () => {
    expect(writesToStudentCanvas(action({
      type: 'SHOW_PARALLEL', presentation_mode: 'PARALLEL',
    }))).toBe(false);
  });

  it('takes the mode from the type when the backend omits it', () => {
    expect(writesToStudentCanvas(action({
      type: 'SHOW_PARALLEL', presentation_mode: null,
    }))).toBe(false);
    expect(writesToStudentCanvas(action({ presentation_mode: null }))).toBe(true);
  });

  it('refuses to draw when the mode contradicts the type', () => {
    // Drift. Guessing which of the two is right is how a worked answer lands on
    // the student's page under the wrong heading — so it is drawn nowhere.
    expect(writesToStudentCanvas(action({ presentation_mode: 'PARALLEL' }))).toBe(false);
    expect(writesToStudentCanvas(action({
      type: 'SHOW_PARALLEL', presentation_mode: 'TUTOR_SOLVED',
    }))).toBe(false);
  });

  it('is false for anything that is not a rescue action', () => {
    expect(writesToStudentCanvas(action({ type: 'HIGHLIGHT' }))).toBe(false);
  });
});
