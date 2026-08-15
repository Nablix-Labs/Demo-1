import { describe, it, expect } from 'vitest';
import {
  clockMayRun,
  shouldClaimNudge,
  onStudentActivity,
  mayPresent,
  markPresented,
  markAcknowledged,
  onDisconnect,
  inLearnerHistory,
  type ActivityGate,
  type InactivityPolicy,
  type NudgeRecord,
} from '@/lib/inactivity';

const POLICY: InactivityPolicy = {
  initialIdleThresholdMs: 20_000,
  cooldownMs: 30_000,
  maxNudgesPerTutorTurn: 2,
};

const IDLE: ActivityGate = {
  studentActive: false,
  requestInFlight: false,
  pageHidden: false,
  disconnected: false,
  awaitingStudent: true,
  tutorTurnFailed: false,
};

const nudge = (over: Partial<NudgeRecord> = {}): NudgeRecord => ({
  id: 'n1',
  state: 'PENDING',
  tutorTurnId: 't1',
  ...over,
});

describe('the idle clock only runs when it should (rules 1, 2)', () => {
  it('runs when the student is idle and the tutor is waiting on them', () => {
    expect(clockMayRun(IDLE)).toBe(true);
  });

  it('does not run before the backend expects a response', () => {
    // Nudging while the tutor still owes a reply blames the student for the
    // tutor being slow.
    expect(clockMayRun({ ...IDLE, awaitingStudent: false })).toBe(false);
  });

  it('does not run after the tutor turn failed', () => {
    // Reported 10 Aug: the student answered "n+6", the tutor returned
    // INTERNAL_ERROR, they answered again, it failed again, they stopped — and
    // were then asked "what is the first thing you would try?". A failed turn
    // leaves awaitingStudent true and lastTutorTurnId on the last turn that
    // worked, so without this the silence is indistinguishable from being stuck.
    expect(clockMayRun({ ...IDLE, tutorTurnFailed: true })).toBe(false);
  });

  it('will not claim after a failed turn even once past the threshold', () => {
    expect(
      shouldClaimNudge({
        policy: POLICY,
        gate: { ...IDLE, tutorTurnFailed: true },
        elapsedMs: 120_000,
        sinceLastNudgeMs: null,
        nudgesThisTurn: 0,
        tutorTurnId: 't1',
      }),
    ).toEqual({ claim: false, reason: 'blocked' });
  });

  it.each([
    ['drawing, typing or speaking', 'studentActive'],
    ['a request in flight', 'requestInFlight'],
    ['the tab hidden', 'pageHidden'],
    ['a dropped connection', 'disconnected'],
  ] as const)('pauses for %s', (_label, key) => {
    expect(clockMayRun({ ...IDLE, [key]: true })).toBe(false);
  });
});

describe('claiming a nudge', () => {
  const base = {
    policy: POLICY,
    gate: IDLE,
    sinceLastNudgeMs: null,
    nudgesThisTurn: 0,
    tutorTurnId: 't1',
  };

  it('claims once past the threshold', () => {
    expect(shouldClaimNudge({ ...base, elapsedMs: 20_000 })).toEqual({
      claim: true,
      reason: 'eligible',
    });
  });

  it('does not claim before the threshold', () => {
    expect(shouldClaimNudge({ ...base, elapsedMs: 19_999 }).reason).toBe('below_threshold');
  });

  it('never invents a policy when the server has not sent one', () => {
    // Explicit validated configuration, no model defaults.
    expect(shouldClaimNudge({ ...base, policy: null, elapsedMs: 999_999 })).toEqual({
      claim: false,
      reason: 'no_policy',
    });
  });

  it('respects the cooldown between nudges', () => {
    expect(
      shouldClaimNudge({ ...base, elapsedMs: 60_000, sinceLastNudgeMs: 29_999 }).reason,
    ).toBe('in_cooldown');
    expect(
      shouldClaimNudge({ ...base, elapsedMs: 60_000, sinceLastNudgeMs: 30_000 }).claim,
    ).toBe(true);
  });

  it('stops at the per-turn maximum (rule 8)', () => {
    expect(shouldClaimNudge({ ...base, elapsedMs: 60_000, nudgesThisTurn: 2 }).reason).toBe(
      'max_reached',
    );
  });

  it('continued silence past the maximum is a no-op, not an escalation', () => {
    for (const elapsedMs of [60_000, 600_000, 3_600_000]) {
      expect(shouldClaimNudge({ ...base, elapsedMs, nudgesThisTurn: 5 }).claim).toBe(false);
    }
  });

  /**
   * A nudge belongs to a tutor turn — NudgeRecord carries its id, and the
   * backend rejects the interaction outright without one:
   * "previous_tutor_turn_id is required for inactivity interactions"
   * (nablix-backend/app/models/interaction.py:85).
   *
   * Claiming anyway posted a request that could only ever 422. Because the
   * controller ticks on an interval it did not do that once, it did it every
   * tick, and each rejection escaped as an uncaught promise (7 Aug, VM).
   */
  it('does not claim before the tutor has taken a turn', () => {
    expect(shouldClaimNudge({ ...base, tutorTurnId: null, elapsedMs: 999_999 })).toEqual({
      claim: false,
      reason: 'no_tutor_turn',
    });
  });

  it('a blocked gate beats an expired clock', () => {
    expect(
      shouldClaimNudge({ ...base, gate: { ...IDLE, studentActive: true }, elapsedMs: 999_999 })
        .reason,
    ).toBe('blocked');
  });
});

describe('activity suppresses a nudge in flight (rules 3, 4)', () => {
  it('activity before presentation suppresses it', () => {
    expect(onStudentActivity(nudge()).state).toBe('SUPPRESSED');
  });

  it('a suppressed nudge is never shown or spoken', () => {
    expect(mayPresent(nudge({ state: 'SUPPRESSED' }))).toBe(false);
  });

  it('a suppressed nudge never enters learner history', () => {
    expect(inLearnerHistory(nudge({ state: 'SUPPRESSED' }))).toBe(false);
  });

  it('ONLY an acknowledged nudge enters learner history', () => {
    // The handoff is explicit: a generated nudge stays outside learner history
    // "until presentation acknowledgement". Until the backend confirms it, the
    // two sides disagree about whether the turn happened, and the frontend must
    // not be the one that decides.
    expect(inLearnerHistory(nudge({ state: 'PRESENTED' }))).toBe(true);
    expect(inLearnerHistory(nudge({ state: 'PRESENTED_UNACKNOWLEDGED' }))).toBe(false);
    expect(inLearnerHistory(nudge({ state: 'PENDING' }))).toBe(false);
  });

  it('activity after presentation does NOT rewrite history', () => {
    // It has already been seen or heard. Pretending otherwise would put the
    // frontend and the backend's records out of step.
    const shown = nudge({ state: 'PRESENTED_UNACKNOWLEDGED' });
    expect(onStudentActivity(shown).state).toBe('PRESENTED_UNACKNOWLEDGED');
    const done = nudge({ state: 'PRESENTED' });
    expect(onStudentActivity(done).state).toBe('PRESENTED');
  });
});

describe('presentation is one-way; only the acknowledgement retries (rules 6, 7)', () => {
  it('pending becomes presented-unacknowledged', () => {
    expect(markPresented(nudge()).state).toBe('PRESENTED_UNACKNOWLEDGED');
  });

  it('a suppressed nudge can never be presented', () => {
    expect(markPresented(nudge({ state: 'SUPPRESSED' })).state).toBe('SUPPRESSED');
  });

  it('presenting twice does not re-show it', () => {
    const once = markPresented(nudge());
    expect(markPresented(once)).toEqual(once);
  });

  it('only the backend acknowledgement completes it', () => {
    expect(markAcknowledged(markPresented(nudge())).state).toBe('PRESENTED');
  });

  it('acknowledgement cannot skip presentation', () => {
    expect(markAcknowledged(nudge()).state).toBe('PENDING');
  });

  it('acknowledging twice is harmless', () => {
    const done = markAcknowledged(markPresented(nudge()));
    expect(markAcknowledged(done)).toEqual(done);
  });
});

describe('disconnect (rule 5)', () => {
  it('suppresses pending nudges rather than holding them', () => {
    const after = onDisconnect([nudge({ id: 'a' }), nudge({ id: 'b' })]);
    expect(after.every((r) => r.state === 'SUPPRESSED')).toBe(true);
  });

  it('leaves already-presented nudges alone', () => {
    const after = onDisconnect([
      nudge({ id: 'a', state: 'PRESENTED' }),
      nudge({ id: 'b', state: 'PRESENTED_UNACKNOWLEDGED' }),
    ]);
    expect(after.map((r) => r.state)).toEqual(['PRESENTED', 'PRESENTED_UNACKNOWLEDGED']);
  });

  it('a nudge claimed before a disconnect never reappears after it', () => {
    // It is about a silence that ended at an unknown time; restoring it would
    // deliver a stale interruption.
    const [restored] = onDisconnect([nudge()]);
    expect(mayPresent(restored)).toBe(false);
  });
});
