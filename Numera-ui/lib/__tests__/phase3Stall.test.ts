/**
 * Issue #309 — "phase3 is not moving to phase 4 or to next question untill i
 * refresh" (Sanya, 14 Sep 2026).
 *
 * The reply that stalled her was a 200 carrying a prerequisite halt, stripped
 * of its event and its routing by `phase3_silent` on the way out, so it reached
 * the browser with no question and no reason. Refreshing fixed it because
 * `GET /session` is not stripped.
 *
 * These pin the one state worth re-reading the session for, and — more
 * importantly — the four neighbouring states that must NOT, because each of
 * them is a screen the student can already see and act on.
 */

import { describe, it, expect } from 'vitest';
import { stalledWithNothingToAnswer } from '@/lib/phase3Stall';

const state = (over: Partial<Parameters<typeof stalledWithNothingToAnswer>[0]> = {}) => ({
  phase: 'INDEPENDENT_PRACTICE',
  questionId: null,
  paused: false,
  interventionStage: 'NONE' as const,
  ...over,
});

describe('a Phase 3 reply that left nothing to answer', () => {
  it('is a stall worth re-reading the session for', () => {
    expect(stalledWithNothingToAnswer(state())).toBe(true);
  });

  it('is not a stall while a question is on screen', () => {
    // The ordinary case, and by far the most common: re-reading here would put
    // a GET on the wire for every turn of Phase 3.
    expect(stalledWithNothingToAnswer(state({ questionId: 'Q-T01-027' }))).toBe(false);
  });

  it('is not a stall once the pause panel is showing', () => {
    // A pause is an ending, not a stall. The panel carries the backend's own
    // sentence; re-reading would fetch the same record and change nothing.
    expect(stalledWithNothingToAnswer(state({ paused: true }))).toBe(false);
  });

  it('is not a stall while the intervention popup is open', () => {
    // §11 asks the student what they are finding difficult. That screen has
    // controls and is waiting on THEM, not on us.
    expect(stalledWithNothingToAnswer(state({ interventionStage: 'COLLECTING' }))).toBe(false);
  });

  it('is not a stall while the topic is held for a human', () => {
    expect(stalledWithNothingToAnswer(state({ interventionStage: 'AWAITING_REVIEW' }))).toBe(false);
  });

  it('ignores every phase but Phase 3, which is the only one that strips', () => {
    // Orientation genuinely has no question of its own — the backend answers
    // `question_id: null` there as a matter of course. Treating that as a stall
    // would fetch the session on arrival at every orientation.
    for (const phase of ['ORIENTATION', 'GUIDED_PRACTICE', 'REVIEW', null, undefined]) {
      expect(stalledWithNothingToAnswer(state({ phase }))).toBe(false);
    }
  });

  it('accepts the phase spellings the backend actually sends', () => {
    // The backend says INDEPENDENT_PRACTICE on the session and
    // PHASE_3_INDEPENDENT_PRACTICE on the event; isPhase3 knows both, and a
    // stall must not depend on which one reached the store.
    expect(stalledWithNothingToAnswer(state({ phase: 'PHASE_3_INDEPENDENT_PRACTICE' }))).toBe(true);
  });

  it('treats an empty question id as no question', () => {
    expect(stalledWithNothingToAnswer(state({ questionId: '' }))).toBe(true);
  });
});
