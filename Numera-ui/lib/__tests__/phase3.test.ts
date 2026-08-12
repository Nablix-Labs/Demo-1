/**
 * Phase 3 silent mode — the acceptance cases from the spec, as tests.
 *
 * Everything here protects the same property: a Phase 3 answer must be evidence
 * of what the student can do ALONE. That fails quietly rather than loudly — a
 * hint that slips through, a lock that lifts on a duplicate reply, or a notice
 * that leaks correctness all still look like a working screen.
 */

import { describe, it, expect } from 'vitest';
import {
  isPhase3, phase3AttemptClosed, phase3Locked, phase3Notice,
  ANSWER_RECORDED, RESCUE_PENDING, OCR_UNCLEAR,
} from '@/lib/phase3';

describe('isPhase3', () => {
  it('recognises the phase under the names the backend has used for it', () => {
    expect(isPhase3('INDEPENDENT_PRACTICE')).toBe(true);
    expect(isPhase3('PHASE_3_INDEPENDENT_PRACTICE')).toBe(true);
    expect(isPhase3('independent_practice')).toBe(true);
  });

  it('is false for every other phase, and for nothing at all', () => {
    // A wrong `true` here silences the tutor during guided practice, where it
    // is supposed to be teaching.
    expect(isPhase3('GUIDED_PRACTICE')).toBe(false);
    expect(isPhase3('CONCEPT_ORIENTATION')).toBe(false);
    expect(isPhase3('REVIEW')).toBe(false);
    expect(isPhase3(null)).toBe(false);
    expect(isPhase3(undefined)).toBe(false);
    expect(isPhase3('')).toBe(false);
  });
});

describe('phase3AttemptClosed', () => {
  it('closes on the backend’s terminal flag', () => {
    expect(phase3AttemptClosed({ independent_attempt_terminal: true })).toBe(true);
  });

  it('closes on a confirmed submission before the terminal flag ships', () => {
    // Spec §1 (the backend half) is not deployed yet; until it is, a confirmed
    // submission is the only signal that the attempt is over.
    expect(phase3AttemptClosed({ phase3_submission_confirmed: true })).toBe(true);
  });

  it('does NOT close when the OCR could not be read', () => {
    // Acceptance: "OCR unclear preserves canvas and leaves attempt unlocked."
    // Losing an attempt to handwriting would be the cruelest possible bug here.
    expect(
      phase3AttemptClosed({ status: 'CLARIFICATION_REQUIRED', independent_attempt_terminal: true }),
    ).toBe(false);
  });

  it('stays open when the backend has said nothing', () => {
    expect(phase3AttemptClosed({})).toBe(false);
    expect(phase3AttemptClosed(null)).toBe(false);
  });
});

describe('phase3Notice', () => {
  it('says only that the answer was recorded', () => {
    expect(phase3Notice({ independent_success: true })).toBe(ANSWER_RECORDED);
    expect(phase3Notice({ independent_outcome: 'CORRECT' })).toBe(ANSWER_RECORDED);
  });

  it('says a fresh check is coming, without naming the outcome', () => {
    expect(phase3Notice({ independent_success: false })).toBe(RESCUE_PENDING);
    expect(phase3Notice({ independent_outcome: 'INCORRECT' })).toBe(RESCUE_PENDING);
  });

  it('reads the renamed outcomes the backend switched to on 11 Aug 2026', () => {
    // CORRECT/INCORRECT became INDEPENDENTLY_VERIFIED/RESCUE_REQUIRED. Both
    // spellings have to work: which one arrives depends on which build is up,
    // and reading the new one as "not a rescue" would drop the rescue notice.
    expect(phase3Notice({ independent_outcome: 'INDEPENDENTLY_VERIFIED' })).toBe(ANSWER_RECORDED);
    expect(phase3Notice({ independent_outcome: 'RESCUE_REQUIRED' })).toBe(RESCUE_PENDING);
  });

  it('stays quiet while a submission is still awaited', () => {
    // AWAITING_SUBMISSION is not a verdict — the attempt is still open.
    expect(phase3AttemptClosed({
      independent_outcome: 'AWAITING_SUBMISSION',
      independent_attempt_terminal: false,
      phase3_submission_confirmed: false,
    })).toBe(false);
  });

  it('asks for a rewrite when the OCR was unreadable', () => {
    expect(phase3Notice({ status: 'CLARIFICATION_REQUIRED' })).toBe(OCR_UNCLEAR);
  });

  it('defaults to the quieter line when the outcome is unknown', () => {
    // With the backend fields absent, guessing "a rescue is coming" would tell
    // the student they got it wrong on no evidence at all.
    expect(phase3Notice({})).toBe(ANSWER_RECORDED);
    expect(phase3Notice(null)).toBe(ANSWER_RECORDED);
  });

  it('never says anything a student could read as a mark', () => {
    for (const res of [
      { independent_success: true },
      { independent_success: false },
      { status: 'CLARIFICATION_REQUIRED' },
      {},
    ]) {
      const line = phase3Notice(res).toLowerCase();
      for (const banned of ['correct', 'incorrect', 'wrong', 'right', 'error', 'well done', 'nice work']) {
        expect(line).not.toContain(banned);
      }
    }
  });
});

describe('phase3Locked', () => {
  it('locks the question the attempt was taken on', () => {
    expect(phase3Locked('Q-1', 'Q-1')).toBe(true);
  });

  it('is unlocked before any attempt', () => {
    expect(phase3Locked(null, 'Q-1')).toBe(false);
  });

  it('unlocks for a rescue or fresh question, and only for it', () => {
    // Acceptance: "Clear the previous lock only for the new question ID."
    expect(phase3Locked('Q-1', 'Q-2-RESCUE')).toBe(false);
  });

  it('a replayed lock for an old question cannot re-lock the new one', () => {
    // Acceptance: "A duplicate or older response cannot unlock or replace newer
    // state." Keying on the id makes a replay a no-op instead of an event.
    const afterRescue = phase3Locked('Q-1', 'Q-2-RESCUE');
    expect(afterRescue).toBe(false);
  });

  it('holds the lock through a reconnect that has not restored the question yet', () => {
    // Acceptance: "Reconnect restores the current locked/new-question state
    // exactly once." Unlocking on a momentarily-null question id would hand the
    // canvas back mid-restore.
    expect(phase3Locked('Q-1', null)).toBe(true);
  });
});

/**
 * All four backend outcomes, handled explicitly.
 *
 * PR #105 (11 Aug 2026) replaced CORRECT/INCORRECT with a four-value enum, and
 * Sanya asked for every value to be handled rather than inferred from the
 * boolean beside it — a build that sends the enum and omits `independent_success`
 * would otherwise read every rescue as a clean pass.
 */
describe('the independent outcome enum', () => {
  const CLOSES = ['INDEPENDENTLY_VERIFIED', 'RESCUE_REQUIRED', 'CORRECT', 'INCORRECT'];
  const LEAVES_OPEN = ['AWAITING_SUBMISSION', 'INPUT_UNCLEAR'];

  it('closes the attempt only on a terminal verdict', () => {
    for (const independent_outcome of CLOSES) {
      expect(phase3AttemptClosed({ independent_outcome })).toBe(true);
    }
    for (const independent_outcome of LEAVES_OPEN) {
      expect(phase3AttemptClosed({ independent_outcome })).toBe(false);
    }
  });

  it('keeps an unreadable attempt open even when the flags say otherwise', () => {
    // The student's handwriting must not cost them the attempt: the enum wins
    // over a terminal flag the backend set beside it.
    expect(phase3AttemptClosed({
      independent_outcome: 'INPUT_UNCLEAR',
      independent_attempt_terminal: true,
      phase3_submission_confirmed: true,
    })).toBe(false);
  });

  it('picks the right line for each outcome without the boolean', () => {
    expect(phase3Notice({ independent_outcome: 'INDEPENDENTLY_VERIFIED' })).toBe(ANSWER_RECORDED);
    expect(phase3Notice({ independent_outcome: 'RESCUE_REQUIRED' })).toBe(RESCUE_PENDING);
    expect(phase3Notice({ independent_outcome: 'INPUT_UNCLEAR' })).toBe(OCR_UNCLEAR);
    expect(phase3Notice({ independent_outcome: 'AWAITING_SUBMISSION' })).toBe(ANSWER_RECORDED);
  });

  it('trusts the enum over a contradicting boolean', () => {
    // Sanya's 12 Aug payload carried both; if they ever disagree the named
    // outcome is the one the backend actually decided on.
    expect(phase3Notice({ independent_outcome: 'RESCUE_REQUIRED', independent_success: true }))
      .toBe(RESCUE_PENDING);
    expect(phase3Notice({ independent_outcome: 'INDEPENDENTLY_VERIFIED', independent_success: false }))
      .toBe(ANSWER_RECORDED);
  });

  it('still reads an older build that sends only the boolean', () => {
    expect(phase3Notice({ independent_success: false })).toBe(RESCUE_PENDING);
    expect(phase3Notice({ independent_success: true })).toBe(ANSWER_RECORDED);
  });

  it('never leaks a verdict for any outcome', () => {
    for (const independent_outcome of [...CLOSES, ...LEAVES_OPEN]) {
      const line = phase3Notice({ independent_outcome }).toLowerCase();
      for (const banned of ['correct', 'incorrect', 'wrong', 'right', 'verified', 'failed']) {
        expect(line).not.toContain(banned);
      }
    }
  });
});
