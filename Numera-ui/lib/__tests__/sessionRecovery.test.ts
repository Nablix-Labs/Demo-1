import { describe, it, expect } from 'vitest';
import {
  requiresSessionRefresh,
  identityOf,
  identityMatches,
  belongsToActiveSession,
  isProgressionRetryRequired,
  type SubmissionIdentity,
} from '@/lib/sessionRecovery';
import type { SessionRecord } from '@/lib/api';

const conflict = (error_code: string, message = '') => ({
  response: { status: 409, data: { error_code, message } },
});

/**
 * Which failures mean "stop, recover, then look again".
 *
 * /interaction answers 409 for several unrelated things, and the difference
 * matters more here than anywhere else: a conflict invalidates the question the
 * student is looking at, so treating an intervention pause as a conflict would
 * silently swap the paused screen for a recovery, and treating a conflict as an
 * ordinary error would leave stale ink pointed at a dead question.
 */
describe('requiresSessionRefresh', () => {
  it('is true for a journey-version conflict', () => {
    expect(requiresSessionRefresh(conflict('JOURNEY_VERSION_CONFLICT'))).toBe(true);
  });

  it('is true for an explicit refresh-required refusal', () => {
    expect(requiresSessionRefresh(conflict('SESSION_STATE_REFRESH_REQUIRED'))).toBe(true);
  });

  it('is false for an intervention pause, which is a different 409', () => {
    // A pause has its own screen and its own read. Recovering it as a conflict
    // would re-enable Check on a topic that is closed to learning actions.
    expect(requiresSessionRefresh(conflict('INTERVENTION_REQUIRED'))).toBe(false);
  });

  it('is false for a content gap, which is a paused state and not a retry', () => {
    expect(requiresSessionRefresh(conflict('CONTENT_GAP'))).toBe(false);
  });

  it('is false for an unrelated 409 with no code we recognise', () => {
    expect(requiresSessionRefresh(conflict('', 'Student Model did not return metadata'))).toBe(false);
  });

  it('is false for the same code on a non-409 status', () => {
    // The code alone is not the signal: a 500 carrying it is a server fault,
    // and recovering from it would hide the fault behind a refresh loop.
    expect(requiresSessionRefresh({
      response: { status: 500, data: { error_code: 'JOURNEY_VERSION_CONFLICT' } },
    })).toBe(false);
  });

  it('is false when nothing arrived at all', () => {
    expect(requiresSessionRefresh(new Error('Network Error'))).toBe(false);
    expect(requiresSessionRefresh(undefined)).toBe(false);
  });
});

const record = (over: Partial<SessionRecord> = {}) => ({
  session_id: 'S1',
  concept_id: 'T01',
  question_id: 'Q-T01-003',
  ...over,
} as SessionRecord);

describe('identityOf', () => {
  it('reads the three fields the session record actually carries', () => {
    expect(identityOf(record())).toEqual({
      sessionId: 'S1',
      topicId: 'T01',
      questionId: 'Q-T01-003',
    });
  });

  it('keeps a null question rather than inventing one', () => {
    // Orientation has no question of its own. Null is a real value here and
    // must compare equal to null, not be coerced to a string.
    expect(identityOf(record({ question_id: null })).questionId).toBeNull();
  });
});

/**
 * The comparison that gates Check.
 *
 * This is the whole point of the recovery: the student's ink belongs to the
 * question they were looking at, and it may only be submitted if recovery came
 * back with that same question. Anything else and the ink is evidence for a
 * question nobody asked.
 */
describe('identityMatches', () => {
  const before: SubmissionIdentity = { sessionId: 'S1', topicId: 'T01', questionId: 'Q-T01-003' };

  it('matches when every field is unchanged', () => {
    expect(identityMatches(before, { ...before })).toBe(true);
  });

  it('does not match when the question changed', () => {
    expect(identityMatches(before, { ...before, questionId: 'Q-T01-004' })).toBe(false);
  });

  it('does not match when the topic changed', () => {
    expect(identityMatches(before, { ...before, topicId: 'T02' })).toBe(false);
  });

  it('does not match when the session changed', () => {
    expect(identityMatches(before, { ...before, sessionId: 'S2' })).toBe(false);
  });

  it('does not match when recovery returned no question', () => {
    // Recovery landing on a phase with no question (orientation, a pause) is
    // not the same question — Check stays disabled rather than submitting into
    // whatever comes next.
    expect(identityMatches(before, { ...before, questionId: null })).toBe(false);
  });

  it('does not treat two absent questions as the same question', () => {
    // Two nulls are not evidence of sameness: neither side names a question, so
    // there is nothing to submit ink against.
    const noQuestion: SubmissionIdentity = { ...before, questionId: null };
    expect(identityMatches(noQuestion, { ...noQuestion })).toBe(false);
  });
});

/**
 * A reply that arrives after the student has moved on.
 *
 * The topic transition is where this bites: Review completes, the client opens
 * the next topic, and an in-flight Review reply or a GET for the OLD session
 * lands afterwards. Applied, it drags the student back to a topic they have
 * finished — and because it carries a real phase and question, nothing
 * downstream can tell it is history.
 *
 * The turn-ordering guard already in place does not catch this: it compares
 * turns within a session, and these replies are correct by that measure. They
 * are wrong by identity, not by order.
 */
describe('belongsToActiveSession', () => {
  const active = { sessionId: 'S2', topicId: 'T02' };

  it('accepts a reply from the session and topic now on screen', () => {
    expect(belongsToActiveSession({ session_id: 'S2', concept_id: 'T02' }, active)).toBe(true);
  });

  it('rejects a reply from the session the student has left', () => {
    expect(belongsToActiveSession({ session_id: 'S1', concept_id: 'T02' }, active)).toBe(false);
  });

  it('rejects a reply from the topic the student has finished', () => {
    expect(belongsToActiveSession({ session_id: 'S2', concept_id: 'T01' }, active)).toBe(false);
  });

  it('accepts a reply that identifies itself only by session', () => {
    // Not every response carries both. Judging it on what it does say beats
    // rejecting it for what it omits.
    expect(belongsToActiveSession({ session_id: 'S2' }, active)).toBe(true);
  });

  it('rejects on the one field it does carry', () => {
    expect(belongsToActiveSession({ session_id: 'S1' }, active)).toBe(false);
  });

  it('accepts a response that identifies itself with neither', () => {
    // Degrade, do not throw: a backend that stops sending a field must not
    // black out the screen. There is nothing to compare, so nothing to reject.
    expect(belongsToActiveSession({}, active)).toBe(true);
  });

  it('accepts anything before a session is active', () => {
    // The first reply of a session arrives while the store still holds nulls.
    expect(belongsToActiveSession(
      { session_id: 'S1', concept_id: 'T01' },
      { sessionId: null, topicId: null },
    )).toBe(true);
  });

  it('ignores blank identifiers rather than treating them as a mismatch', () => {
    expect(belongsToActiveSession({ session_id: '', concept_id: '  ' }, active)).toBe(true);
  });
});

/**
 * 503 PROGRESSION_RETRY_REQUIRED — the engine was unreachable mid-progression.
 *
 * Retryable and SAFE, which is the unusual part. The follow-up event is already
 * persisted, so a retry re-sends the identical event and nothing is graded or
 * counted twice. The student's work is saved.
 *
 * It can come back from GET /session itself — the one route the client is told
 * to call to recover — so "the read failed" cannot mean "give up here".
 */
describe('isProgressionRetryRequired', () => {
  const at = (status: number, error_code: string) => ({
    response: { status, data: { error_code, message: '' } },
  });

  it('recognises the retryable progression failure', () => {
    expect(isProgressionRetryRequired(at(503, 'PROGRESSION_RETRY_REQUIRED'))).toBe(true);
  });

  it('is not an ordinary 503', () => {
    // A plain 503 is not known to be safe to retry. Only the code says so.
    expect(isProgressionRetryRequired(at(503, ''))).toBe(false);
  });

  it('is not the same code on another status', () => {
    expect(isProgressionRetryRequired(at(500, 'PROGRESSION_RETRY_REQUIRED'))).toBe(false);
  });

  it('is not a conflict, and a conflict is not it', () => {
    // Different envelopes, different client actions: REFRESH versus RETRY.
    expect(isProgressionRetryRequired(at(409, 'JOURNEY_VERSION_CONFLICT'))).toBe(false);
    expect(requiresSessionRefresh(at(503, 'PROGRESSION_RETRY_REQUIRED'))).toBe(false);
  });

  it('is false when nothing arrived', () => {
    expect(isProgressionRetryRequired(new Error('Network Error'))).toBe(false);
  });
});
