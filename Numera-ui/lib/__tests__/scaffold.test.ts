/**
 * Phase 2 scaffolding — the acceptance tests from §10 of the frontend handoff.
 *
 * These matter more than most because the failures they guard against are
 * INVISIBLE in a demo: a leaked expected answer looks like nothing at all until
 * a student reads the DOM, and a locally-incremented step number looks correct
 * right up to the point it silently disagrees with the Student Model.
 *
 * The tests run against `activeScaffold`, which is the single place that decides
 * whether a panel is open and what is in it.
 */

import { describe, it, expect } from 'vitest';
import { activeScaffold, type InteractionResponse } from '@/lib/api';

/** A realistic first scaffold step — the worked example from §4 of the handoff. */
function stepOne(over: Partial<InteractionResponse> = {}): InteractionResponse {
  return {
    session_id: 'SESSION015',
    student_id: 'ST015',
    current_phase: 'GUIDED_PRACTICE',
    current_question: 'Solve for x: ½x = 4',
    question_id: 'ALG_1STEP_GP_F01',
    interaction_mode: 'TEXT',
    message: 'Which number is multiplying x?',
    message_voice: 'Which number is multiplying x?',
    hint_count: 0,
    phase_indicator: 'GUIDED_PRACTICE',
    show_scaffold_panel: true,
    scaffold_id: 'SCF-T02-FRACTIONAL-COEFFICIENT',
    current_scaffold_step_id: 'SCF-T02-FC-S1',
    scaffold_step_number: 1,
    scaffold_step_text: 'Which number is multiplying x?',
    scaffold_step_voice: 'Which number is multiplying x?',
    total_scaffold_steps: 3,
    conversation_action: 'DELIVER_SCAFFOLD_STEP',
    expects_student_response: true,
    ...over,
  };
}

describe('scaffold: one authorised step at a time', () => {
  it('opens the panel on exactly the step the backend authorised', () => {
    expect(activeScaffold(stepOne())).toEqual({
      scaffoldId: 'SCF-T02-FRACTIONAL-COEFFICIENT',
      currentStepId: 'SCF-T02-FC-S1',
      stepNumber: 1,
      stepText: 'Which number is multiplying x?',
      stepVoice: 'Which number is multiplying x?',
      totalSteps: 3,
    });
  });

  it('reports position without exposing any later step', () => {
    const s = activeScaffold(stepOne())!;
    expect(s.totalSteps).toBe(3);
    // The only step text present anywhere is the authorised one.
    expect(Object.values(s).join(' ')).not.toMatch(/step 2|step 3/i);
  });

  it('replaces the panel when a NEW step id arrives', () => {
    const next = activeScaffold(
      stepOne({
        current_scaffold_step_id: 'SCF-T02-FC-S2',
        scaffold_step_number: 2,
        scaffold_step_text: 'So what do we do to both sides?',
        scaffold_step_voice: null,
      }),
    )!;
    expect(next.currentStepId).toBe('SCF-T02-FC-S2');
    expect(next.stepNumber).toBe(2);
    expect(next.stepText).toBe('So what do we do to both sides?');
  });

  it('does not advance on a retry of the SAME step', () => {
    // Backend retries step 1 with different guidance; the step must not move on.
    const retry = activeScaffold(
      stepOne({ message: 'Not quite — look at the fraction in front of x.' }),
    )!;
    expect(retry.currentStepId).toBe('SCF-T02-FC-S1');
    expect(retry.stepNumber).toBe(1);
  });

  it('closes the panel when show_scaffold_panel is false', () => {
    expect(activeScaffold(stepOne({ show_scaffold_panel: false }))).toBeNull();
  });

  it('leaves no stale step when the backend sends a panel with no step', () => {
    // A partial or malformed response must close the panel, not keep the last
    // step on screen next to an unrelated tutor message.
    expect(activeScaffold(stepOne({ scaffold_step_text: null }))).toBeNull();
    expect(activeScaffold(stepOne({ current_scaffold_step_id: null }))).toBeNull();
    expect(activeScaffold(stepOne({ scaffold_step_text: '   ' }))).toBeNull();
  });

  it('stays closed for an ordinary turn and for a backend that has no scaffolding yet', () => {
    const plain = stepOne();
    delete plain.show_scaffold_panel;
    expect(activeScaffold(plain)).toBeNull();
    expect(activeScaffold(null)).toBeNull();
    expect(activeScaffold(undefined)).toBeNull();
  });
});

describe('scaffold: voice follows the authorised step', () => {
  it('prefers the step voice line', () => {
    expect(activeScaffold(stepOne())!.stepVoice).toBe('Which number is multiplying x?');
  });

  it('reports no step voice when the backend omits it, so the caller speaks the message', () => {
    expect(activeScaffold(stepOne({ scaffold_step_voice: null }))!.stepVoice).toBeNull();
    expect(activeScaffold(stepOne({ scaffold_step_voice: '  ' }))!.stepVoice).toBeNull();
  });
});

describe('scaffold: nothing tutor-only reaches the student', () => {
  it('carries no expected response, canonical answer, or step catalogue', () => {
    // Simulate a backend that leaks private fields anyway — the shape the UI
    // receives must still contain none of them.
    const leaky = stepOne() as InteractionResponse & Record<string, unknown>;
    leaky.expected_response = 'one half';
    leaky.canonical_answer = 'x = 8';
    leaky.tutor_view = { accepted_answers: ['8'] };
    leaky.scaffold_steps = [
      { id: 'SCF-T02-FC-S1', text: 'Which number is multiplying x?' },
      { id: 'SCF-T02-FC-S2', text: 'So what do we do to both sides?' },
      { id: 'SCF-T02-FC-S3', text: 'What is x?' },
    ];

    const s = activeScaffold(leaky)!;
    const serialised = JSON.stringify(s);

    expect(Object.keys(s).sort()).toEqual([
      'currentStepId', 'scaffoldId', 'stepNumber', 'stepText', 'stepVoice', 'totalSteps',
    ]);
    expect(serialised).not.toMatch(/one half|x = 8|accepted_answers|both sides|What is x/i);
  });
});

describe('scaffold: the backend uses 0 as "unset", not null', () => {
  // app/models/interaction.py types scaffold_step_number and
  // total_scaffold_steps as `int = 0` (landed 2026-07-29 in #46/#47). A `?? 1`
  // fallback only catches null, so an ordinary turn with no scaffold running
  // would have rendered "Step 0 of 0".
  it('treats 0 as unset rather than showing step zero', () => {
    const s = activeScaffold(stepOne({ scaffold_step_number: 0, total_scaffold_steps: 0 }))!;
    expect(s.stepNumber).toBe(1);
    expect(s.totalSteps).toBe(1);
  });

  it('never claims a step beyond the total', () => {
    const s = activeScaffold(stepOne({ scaffold_step_number: 2, total_scaffold_steps: 0 }))!;
    expect(s.stepNumber).toBe(2);
    expect(s.totalSteps).toBe(2);
  });
});
