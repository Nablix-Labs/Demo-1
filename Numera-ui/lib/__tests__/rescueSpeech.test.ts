/**
 * Every rescue step is spoken exactly once.
 *
 * "Exactly" is two failures, not one, and they look nothing alike: a step
 * spoken twice is the tutor stammering, a step spoken never is the silent
 * "Let me show you" that started this work.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  nextUnspokenStep, speakRescueStep, hasSpokenRescueStep, forgetSpokenRescueSteps,
} from '@/lib/rescueSpeech';
import type { RescueStep } from '@/lib/rescueActions';

const step = (stepIndex: number, rescueId = 'R1'): RescueStep => ({
  actionId: `${rescueId}:A${stepIndex}`,
  rescueId,
  mode: 'TUTOR_SOLVED',
  stepIndex,
  totalSteps: 3,
  text: `Step ${stepIndex}.`,
  anchorId: `TUTOR_ANCHOR:RESCUE:${rescueId}:STEP:${stepIndex}`,
  returnTargetObjectId: null,
  answerReveal: false,
  sourceId: null,
});

/** Stands in for tutorSay: records what was said, reports that audio started. */
const speaker = () => {
  const said: string[] = [];
  return { said, say: (text: string) => { said.push(text); return true; } };
};

beforeEach(forgetSpokenRescueSteps);

describe('choosing what to say', () => {
  it('says nothing when no step has arrived', () => {
    expect(nextUnspokenStep([])).toBeNull();
  });

  it('picks the step that just arrived', () => {
    expect(nextUnspokenStep([step(1)])?.stepIndex).toBe(1);
  });

  it('picks the newest when several land together', () => {
    // A queued action released by a render, or a reconnect delivering a
    // backlog. The student is looking at the last one; narrating the one
    // before it would describe a mark that is no longer the subject.
    expect(nextUnspokenStep([step(1), step(2)])?.stepIndex).toBe(2);
  });

  it('has nothing left to say once the newest has been said', () => {
    const { say } = speaker();
    speakRescueStep(step(2), say);
    expect(nextUnspokenStep([step(1), step(2)])).toBeNull();
  });
});

describe('saying it', () => {
  it('speaks a new step', () => {
    const { said, say } = speaker();
    speakRescueStep(step(1), say);
    expect(said).toEqual(['Step 1.']);
  });

  it('does not speak the same step twice', () => {
    // The replay cases this absorbs: a reconnect re-sending the current step,
    // mergeStep replacing it in place, and React re-rendering for reasons that
    // have nothing to do with the tutor.
    const { said, say } = speaker();
    speakRescueStep(step(1), say);
    speakRescueStep(step(1), say);
    expect(said).toEqual(['Step 1.']);
  });

  it('speaks each step of a walkthrough, in order', () => {
    const { said, say } = speaker();
    for (const i of [1, 2, 3]) speakRescueStep(step(i), say);
    expect(said).toEqual(['Step 1.', 'Step 2.', 'Step 3.']);
  });

  it('speaks step 1 of a NEW rescue, even though the index repeats', () => {
    // Keyed on the action id, not the index. B's step 1 is not A's step 1, and
    // a student whose rescue was superseded must hear the replacement open.
    const { said, say } = speaker();
    speakRescueStep(step(1, 'R1'), say);
    speakRescueStep(step(1, 'R2'), say);
    expect(said).toEqual(['Step 1.', 'Step 1.']);
  });

  it('speaks two steps whose text happens to match', () => {
    const { said, say } = speaker();
    const a = { ...step(1), text: 'Now divide.' };
    const b = { ...step(2), text: 'Now divide.' };
    speakRescueStep(a, say);
    speakRescueStep(b, say);
    expect(said).toEqual(['Now divide.', 'Now divide.']);
  });

  it('does not retry a step the tutor was not allowed to say', () => {
    // tutorSay reports false when the student has the floor (they are writing,
    // §1). That is a decision not to say THIS step, not a failure — retrying it
    // would wait for the pen to lift and then narrate a step the student has
    // already read and possibly already advanced past.
    const silenced = vi.fn(() => false);
    speakRescueStep(step(1), silenced);
    expect(hasSpokenRescueStep('R1:A1')).toBe(true);
    expect(nextUnspokenStep([step(1)])).toBeNull();
  });
});
