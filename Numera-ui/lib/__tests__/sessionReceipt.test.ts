/**
 * The end-of-session receipt reads its totals from
 * `session_summary.session_performance` — the backend's own counters — and from
 * nowhere else.
 *
 * It used to fall back to `attempt_count`, which is the CURRENT QUESTION's
 * counter, and then to `canvas_submissions.length`, which counts submissions
 * rather than attempts. Both produced a plausible number that was not the one
 * it claimed to be. `total_attempts` also used to count every phase together —
 * two Phase 3 answers and eleven Guided read as thirteen — which is what
 * `independent_attempts` (backend PR #235) now separates out.
 */
import { describe, expect, it } from 'vitest';
import { toSessionSummary } from '@/lib/api';

const performance = {
  total_attempts: 13,
  correct_attempts: 9,
  incorrect_attempts: 4,
  hints_used: 3,
  hint_levels_used: [1, 2, 1],
  canvas_submissions: 5,
  independent_attempts: 2,
};

const ended = (over: Record<string, unknown> = {}) =>
  ({
    session_id: 'S1',
    student_id: 'ST001',
    concept_id: 'ALG_LINEAR_ONE_STEP',
    status: 'ended',
    current_question: 'n + 5',
    session_summary: { session_performance: performance },
    ...over,
  }) as never;

describe('the end-of-session receipt', () => {
  it('takes every total from session_performance', () => {
    const s = toSessionSummary(ended())!;
    expect(s.performance).toEqual({
      total_attempts: 13,
      correct_attempts: 9,
      incorrect_attempts: 4,
      hints_used: 3,
      canvas_submissions: 5,
      independent_attempts: 2,
    });
  });

  it('does not substitute the current question attempt_count', () => {
    // attempt_count is the question the student happened to end on. It used to
    // win here, so a 13-attempt session could report 2.
    const s = toSessionSummary(ended({ attempt_count: 2 }))!;
    expect(s.performance?.total_attempts).toBe(13);
  });

  it('does not substitute canvas_submissions.length for attempts', () => {
    const s = toSessionSummary(
      ended({ canvas_submissions: [{}, {}, {}, {}, {}, {}, {}] }),
    )!;
    expect(s.performance?.total_attempts).toBe(13);
  });

  it('reports performance as null rather than guessing when the backend omits it', () => {
    // Degrade, never invent: a wrong total presented as authoritative is worse
    // than an absent one, and this screen is the student's record of the session.
    const s = toSessionSummary(
      ended({ session_summary: undefined, attempt_count: 2, hint_count: 1 }),
    )!;
    expect(s.performance).toBeNull();
  });

  it('still returns null for a response with no session', () => {
    expect(toSessionSummary(null)).toBeNull();
    expect(toSessionSummary({} as never)).toBeNull();
  });
});
