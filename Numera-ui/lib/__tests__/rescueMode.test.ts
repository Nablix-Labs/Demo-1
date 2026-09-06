/**
 * Rescue exclusivity — the rule that stops two panels being one rescue.
 *
 * Each of these was a real disagreement between two components that were each
 * deciding "is a rescue running" on their own evidence.
 */

import { describe, it, expect } from 'vitest';
import {
  rescueActive, legacyRescueVisible, currentRescueStep, rescueBlocksSubmission,
  panelCarriesStepText,
  type RescueModeState,
} from '@/lib/rescueMode';
import { writesToStudentCanvas } from '@/lib/rescueActions';
import type { RescueStep } from '@/lib/rescueActions';
import type { GuidedRescuePayload } from '@/lib/guidedRescue';

const step = (stepIndex: number, rescueId = 'R1'): RescueStep => ({
  actionId: `A${stepIndex}`,
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

const legacy: GuidedRescuePayload = {
  rescue_type: 'TUTOR_SOLVED',
  tutor_solved: {
    explanation: 'Here is one done.',
    final_answer: 'x = 4',
    answer_steps: ['Subtract 6.', 'Divide by 3.'],
  },
};

const state = (over: Partial<RescueModeState> = {}): RescueModeState => ({
  rescueSteps: [],
  guidedRescue: null,
  currentPhase: 'GUIDED_PRACTICE',
  ...over,
});

describe('is a rescue running', () => {
  it('is not, with nothing served', () => {
    expect(rescueActive(state())).toBe(false);
  });

  it('is, as soon as one step has rendered', () => {
    expect(rescueActive(state({ rescueSteps: [step(1)] }))).toBe(true);
  });

  it('is not in Phase 3, whatever arrived', () => {
    // Phase 3 is answered alone (spec §3.2). The store already refuses to
    // record rescue actions there; this agrees with it rather than assuming it
    // ran first, because the two disagreeing is precisely the class of bug
    // this module exists to remove.
    expect(rescueActive(state({
      rescueSteps: [step(1)], currentPhase: 'INDEPENDENT_PRACTICE',
    }))).toBe(false);
  });
});

describe('which implementation may render', () => {
  it('shows the legacy card when only the legacy payload was served', () => {
    expect(legacyRescueVisible(state({ guidedRescue: legacy }))).toBe(true);
  });

  it('hides the legacy card the moment a stepwise step exists', () => {
    // The reported defect: both panels for one rescue. The legacy payload
    // carries every step INCLUDING the answer, so showing it beside a
    // walkthrough that is releasing steps one at a time does not merely
    // duplicate the panel — it hands over the answer the walkthrough is
    // deliberately withholding.
    expect(legacyRescueVisible(state({
      guidedRescue: legacy, rescueSteps: [step(1)],
    }))).toBe(false);
  });

  it('never shows both at once, on any combination', () => {
    for (const rescueSteps of [[], [step(1)]]) {
      for (const guidedRescue of [null, legacy]) {
        const s = state({ rescueSteps, guidedRescue });
        expect(rescueActive(s) && legacyRescueVisible(s)).toBe(false);
      }
    }
  });

  it('hides the legacy card in Phase 3 too', () => {
    expect(legacyRescueVisible(state({
      guidedRescue: legacy, currentPhase: 'INDEPENDENT_PRACTICE',
    }))).toBe(false);
  });
});

describe('the step on screen', () => {
  it('is the newest one, not the first', () => {
    // The panel shows one step; the canvas keeps the earlier marks. A
    // tutor-solved rescue IS the tutor working down the page, so the written
    // column accumulates while the panel does not.
    expect(currentRescueStep(state({
      rescueSteps: [step(1), step(2)],
    }))?.stepIndex).toBe(2);
  });

  it('is null when no rescue is running', () => {
    expect(currentRescueStep(state())).toBeNull();
    expect(currentRescueStep(state({
      rescueSteps: [step(1)], currentPhase: 'INDEPENDENT_PRACTICE',
    }))).toBeNull();
  });
});

describe('normal submission during a rescue', () => {
  it('is blocked while a rescue is on screen', () => {
    // A normal answer sent here is evaluated against the ORIGINAL question,
    // which re-opens the scaffold the rescue was escalated past — so the
    // student answers, is marked on the question they were stuck on, and the
    // rescue they were reading is replaced by the rung above it.
    expect(rescueBlocksSubmission(state({ rescueSteps: [step(1)] }))).toBe(true);
  });

  it('is allowed again once the rescue is cleared', () => {
    expect(rescueBlocksSubmission(state())).toBe(false);
  });
});

describe('panelCarriesStepText — who owns the words', () => {
  // The bug: one TUTOR_SOLVED_STEP action was rendered on two surfaces at once.
  // The store writes action.text onto the tutor layer (actionMarks, the
  // rescue-slot branch) AND hands the same text to the panel via rescueStep, so
  // the current step appeared as ink on the canvas and again in the sticky note
  // — "its writing twice" (Manjusha, 6 Sep).
  const modeStep = (mode: 'PARALLEL' | 'TUTOR_SOLVED') =>
    ({ actionId: 'A1', rescueId: 'R1', mode, stepIndex: 1 } as RescueStep);

  it('leaves the words to the canvas for a tutor-solved step', () => {
    // writesToStudentCanvas is true here, so the canvas already has them.
    expect(panelCarriesStepText(modeStep('TUTOR_SOLVED'))).toBe(false);
  });

  it('keeps them in the panel for a parallel example', () => {
    // A parallel example is a DIFFERENT problem and is deliberately never
    // written onto the page the student is working on, so the panel is its only
    // surface. Dropping the text here would leave a step counter and nothing
    // to read — a worse bug than the one being fixed.
    expect(panelCarriesStepText(modeStep('PARALLEL'))).toBe(true);
  });

  it('says no when there is no step at all', () => {
    expect(panelCarriesStepText(null)).toBe(false);
    expect(panelCarriesStepText(undefined)).toBe(false);
  });

  it('agrees with writesToStudentCanvas for every mode', () => {
    // The two must never disagree about which surface is carrying the words.
    // Asserted against the canvas's own predicate rather than restating the
    // rule, so a change to one that is not made to the other fails here.
    (['PARALLEL', 'TUTOR_SOLVED'] as const).forEach((mode) => {
      const action = {
        type: mode === 'PARALLEL' ? 'SHOW_PARALLEL' : 'TUTOR_SOLVED_STEP',
        presentation_mode: mode,
      } as never;
      expect(panelCarriesStepText(modeStep(mode))).toBe(!writesToStudentCanvas(action));
    });
  });
});
