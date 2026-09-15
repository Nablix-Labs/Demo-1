/**
 * Issue #304 — "Tutor writes on canvas to confirm what the student said but
 * with out completing immediately moves to next question /sections" (Sanya,
 * 14 Sep 2026).
 *
 * The board was held for a flat 900ms while the writing itself takes
 * `max(700, chars × 95)`ms per mark. The tutor was cut off mid-word.
 *
 * The regression test that matters is the last one in the first block: a
 * realistic confirmation must need MORE than the old constant, because that is
 * the whole bug.
 */

import { describe, it, expect } from 'vitest';
import {
  elementWritingMs, outstandingWritingMs, GAP_MS, MAX_HOLD_MS,
} from '@/lib/tutorWritingTime';
import { revealDecision } from '@/lib/revealBeforeClear';
import type { TutorElement } from '@/store/useNumeraStore';

const text = (id: string, content: string): TutorElement => ({
  id, kind: 'text', text: content, x: 0.1, y: 0.2,
});

/** The old flat hold, kept here only as the thing being regressed against. */
const OLD_FLAT_HOLD_MS = 900;

describe('the hold must outlast the writing', () => {
  it('scales with how much there is to write', () => {
    const short = elementWritingMs(text('a', 'n'));
    const long = elementWritingMs(text('a', 'Start: n, Gain: +5, so n + 5'));
    expect(long).toBeGreaterThan(short);
  });

  it('gives even a one-character mark time to be seen', () => {
    expect(elementWritingMs(text('a', 'n'))).toBeGreaterThan(600);
  });

  it('needs longer than the old flat hold for a realistic confirmation', () => {
    // THE REGRESSION. "Start: n, Gain: +5" is the kind of line the tutor writes
    // to confirm what the student said — the exact case in #304. At 95ms a
    // character it takes ~1.7s; the board used to be released at 900ms, so the
    // student watched it get cut off on the way to the next question.
    const confirmation = [text('m1', 'Start: n'), text('m2', 'Gain: +5')];
    const needed = outstandingWritingMs(confirmation, {}, false);
    expect(needed).toBeGreaterThan(OLD_FLAT_HOLD_MS);
  });

  it('holds for the whole batch, not just the first mark', () => {
    const one = outstandingWritingMs([text('m1', 'Start: n')], {}, false);
    const two = outstandingWritingMs([text('m1', 'Start: n'), text('m2', 'Gain: +5')], {}, false);
    expect(two).toBeGreaterThan(one);
  });

  it('leaves a breath between marks, but not after a lone one', () => {
    // Compared against each mark's own duration rather than doubling one of
    // them: the tempo jitter is per-id, so two marks with the same text do not
    // take the same time.
    const a = text('m1', 'abc');
    const b = text('m2', 'abc');
    expect(outstandingWritingMs([a], {}, false)).toBeCloseTo(elementWritingMs(a), 5);
    expect(outstandingWritingMs([a, b], {}, false))
      .toBeCloseTo(elementWritingMs(a) + elementWritingMs(b) + GAP_MS, 5);
  });
});

describe('what is still owed on the board', () => {
  it('counts a mark the sequencer has not picked up yet, in full', () => {
    // The case that matters: the sequencer runs from an effect AFTER the store
    // write, so the confirmation being written right now is not in `progress`
    // at the moment the hold is decided. Absent must mean "all of it to come",
    // never "nothing to wait for".
    const el = text('m1', 'Start: n');
    expect(outstandingWritingMs([el], {}, false)).toBeCloseTo(elementWritingMs(el), 5);
  });

  it('counts only what is left of a mark mid-write', () => {
    const el = text('m1', 'Start: n');
    const half = outstandingWritingMs([el], { m1: 0.5 }, false);
    expect(half).toBeCloseTo(elementWritingMs(el) * 0.5, 5);
  });

  it('owes nothing for writing that has finished', () => {
    // A board carrying marks from earlier turns must not hold the next
    // question back — they were written and read long ago.
    expect(outstandingWritingMs([text('m1', 'old')], { m1: 1 }, false)).toBe(0);
  });

  it('owes nothing on an empty board', () => {
    expect(outstandingWritingMs([], {}, false)).toBe(0);
  });

  it('waits for nothing under reduced motion, where everything is instant', () => {
    const marks = [text('m1', 'Start: n'), text('m2', 'Gain: +5')];
    expect(outstandingWritingMs(marks, {}, true)).toBe(0);
  });
});

describe('the hold still refuses every case it refused before', () => {
  it('holds a completing turn for as long as the writing needs', () => {
    const needed = outstandingWritingMs([text('m1', 'Start: n')], {}, false);
    expect(revealDecision(needed, 'Q1', 'Q2')).toEqual({ reveal: true, holdMs: needed });
  });

  it('does not hold when nothing is being written — a pause with nothing in it', () => {
    expect(revealDecision(0, 'Q1', 'Q2')).toEqual({ reveal: false, holdMs: 0 });
  });

  it('does not hold when the question is not changing', () => {
    // Nothing is about to be cleared, so there is nothing to outrun.
    expect(revealDecision(3000, 'Q1', 'Q1')).toEqual({ reveal: false, holdMs: 0 });
  });

  it('does not hold on the first question of a session', () => {
    expect(revealDecision(3000, null, 'Q1').reveal).toBe(false);
  });

  it('does not hold when the reply names no next question', () => {
    // A null question id does not mean "move on" — applyBackendPhase decides
    // what that means per phase, and delaying it here would guess.
    expect(revealDecision(3000, 'Q1', null).reveal).toBe(false);
    expect(revealDecision(3000, 'Q1', undefined).reveal).toBe(false);
    expect(revealDecision(3000, 'Q1', '').reveal).toBe(false);
  });

  it('caps a pathological batch rather than freezing the lesson', () => {
    // The hold is derived from content now, and content comes from a model. A
    // ten-second pause on a finished question is a worse failure than the one
    // being fixed: the writing has visibly stopped and there is no way on.
    expect(revealDecision(60_000, 'Q1', 'Q2').holdMs).toBe(MAX_HOLD_MS);
  });
});
