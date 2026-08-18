/**
 * A cancelled tutor reply has to hand the turn back — or deliberately not.
 *
 * The audio half of barge-in is the obvious part; the turn half is the part
 * that breaks. Tutor audio that is cut off never reaches idle, so the handler
 * that normally opens the next student turn never runs, and the barged-in turn
 * reaches the server carrying the previous turn's `turn_id` (Aditya, 14 Aug
 * 2026 — the same failure lib/voiceTurnContext was written for).
 *
 * Which is why these assert on the reopen decision rather than on silence: a
 * handler that stops the audio and stops there is the bug.
 */

import { describe, expect, it } from 'vitest';
import { reopensStudentTurn } from '@/lib/tutorAudioCancel';

describe('a cancelled tutor reply', () => {
  it('reopens the turn when the student talked over it', () => {
    expect(reopensStudentTurn({ reason: 'barge_in', expect_new_turn: true })).toBe(true);
  });

  it('does not reopen when a typed answer replaced it', () => {
    // The REST path already minted a turn via beginSubmissionTurn; a second one
    // here would replace the id the answer was submitted under.
    expect(reopensStudentTurn({ reason: 'superseded_by_text', expect_new_turn: false })).toBe(false);
  });

  it('follows the flag, not the reason, when the two disagree', () => {
    // The server owns this decision so a third reason cannot require a frontend
    // release to learn its turn semantics. Reading `reason` first would defeat
    // the whole point of the flag.
    expect(reopensStudentTurn({ reason: 'barge_in', expect_new_turn: false })).toBe(false);
    expect(reopensStudentTurn({ reason: 'superseded_by_text', expect_new_turn: true })).toBe(true);
  });
});

describe('a frame with no flag on it', () => {
  it('still reopens after a barge-in', () => {
    // Defaulting to false here would silently restore the missing-turn-context
    // bug this frame exists to prevent — and it would fail on the ONE reason
    // that cannot survive being got wrong.
    expect(reopensStudentTurn({ reason: 'barge_in' })).toBe(true);
  });

  it('leaves a superseded reply alone', () => {
    expect(reopensStudentTurn({ reason: 'superseded_by_text' })).toBe(false);
  });

  it('leaves an unrecognised reason alone', () => {
    // Minting a turn for a reason we do not understand is the more damaging
    // guess: it overwrites a turn id that something else may be relying on.
    expect(reopensStudentTurn({ reason: 'tts_quota_exhausted' })).toBe(false);
    expect(reopensStudentTurn({})).toBe(false);
  });

  it('is not fooled by a truthy non-boolean flag', () => {
    // A server that sends "true" as a string has not answered the question, so
    // fall through to the reason rather than trusting the coercion.
    expect(reopensStudentTurn({ reason: 'superseded_by_text', expect_new_turn: 'true' as never })).toBe(false);
  });
});
