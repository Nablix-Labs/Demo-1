import { describe, it, expect } from 'vitest';
import { studentFacingError, voiceTurnFailedMessage, isStaleSessionError } from '@/lib/api';

/**
 * A failure should say what actually failed.
 *
 * Every status that fell through used to return null, so the caller showed
 * "Sorry — I couldn't reach the tutor just now." That sentence describes a
 * network problem. A 500 or a 422 is not a network problem — the request
 * arrived and the server rejected or broke on it — and calling it unreachable
 * sends whoever is testing to look at the frontend and the wifi while the real
 * fault sits in a service log nobody opened.
 *
 * This is about the next person spending their time in the right place.
 */
const err = (status: number, data?: Record<string, unknown>) => ({ response: { status, data } });

describe('server-side failures are named as server-side', () => {
  it('a 500 does not read as unreachable', () => {
    const msg = studentFacingError(err(500));
    expect(msg).toBeTruthy();
    expect(msg).toMatch(/tutor service/i);
    expect(msg).not.toMatch(/reach/i);
  });

  it('a 502 never exposes an internal provider explanation to the student', () => {
    const message = studentFacingError(err(502, {
      message: 'status=400 body={"error":{"message":"invalid_json_schema"}}',
    }));
    expect(message).toMatch(/tutor service/i);
    expect(message).not.toMatch(/status=|body=|invalid_json_schema/i);
  });

  it('a 504 is reported as a timeout, not a connection failure', () => {
    expect(studentFacingError(err(504))).toMatch(/too long/i);
  });

  it('a 429 tells the student to wait rather than retry immediately', () => {
    expect(studentFacingError(err(429))).toMatch(/lot right now|few seconds/i);
  });
});

describe('client-side and contract failures', () => {
  it('a 422 does not invite an endless retry loop', () => {
    // Retrying a contract mismatch fails identically every time.
    const msg = studentFacingError(err(422));
    expect(msg).toMatch(/team/i);
    expect(msg).not.toMatch(/try again/i);
  });

  it('a 403 explains it is the wrong student, not a broken tutor', () => {
    expect(studentFacingError(err(403))).toMatch(/different student/i);
  });

  it('an unmapped 4xx still surfaces the backend message', () => {
    expect(studentFacingError(err(400, { message: 'question_id is required' })))
      .toContain('question_id is required');
  });
});

describe('the cases that were already right stay right', () => {
  it('auth failure asks the student to sign in', () => {
    expect(studentFacingError(err(401, { error_code: 'AUTHENTICATION_FAILED' })))
      .toMatch(/signed in|log in/i);
  });

  it('a 409 resume case says the topic is already in progress', () => {
    expect(studentFacingError(err(409, { message: 'Topic already in progress' })))
      .toMatch(/already have this topic/i);
  });

  it('a 409 that is NOT the resume case does not claim it is', () => {
    // The ALG_1STEP_GP_F01 lesson: a confident wrong resume explanation sent
    // the team looking in the wrong place for two days. The actual adapter
    // detail remains in diagnostics, but must not be placed in learner chat.
    const msg = studentFacingError(
      err(409, { message: 'Student Model did not return metadata for ALG_1STEP_GP_F01' }),
    );
    expect(msg).not.toMatch(/already have this topic/i);
    expect(msg).toMatch(/tutor hit a problem/i);
    expect(msg).not.toContain('ALG_1STEP_GP_F01');
  });

  it('never exposes a Student Model error-code rejection in learner chat', () => {
    const msg = studentFacingError(
      err(409, {
        error_code: 'INVALID_ERROR_CODE',
        message: 'student_model rejected request url=https://nablix.ai:8080/session/event status=409 body={"error_code":"INVALID_ERROR_CODE","message":"error_code UNKNOWN_ERROR is not valid for question Q-T01-002."}',
      }),
    );
    expect(msg).toMatch(/tutor hit a problem/i);
    expect(msg).not.toMatch(/student_model|UNKNOWN_ERROR|Q-T01-002|session\/event|8080/i);
  });

  it('a journey-version conflict never exposes the stored journey payload', () => {
    const msg = studentFacingError(
      err(409, {
        error_code: 'JOURNEY_VERSION_CONFLICT',
        message: "{'current_journey_state': {'student_id': 'ST016', 'version': 8}}",
      }),
    );
    expect(msg).toMatch(/two submissions|press Check/i);
    expect(msg).not.toContain('current_journey_state');
    expect(msg).not.toContain('student_id');
  });
});

describe('a genuinely unreachable server still reads as unreachable', () => {
  it('returns null when no response ever arrived, so the caller uses its network copy', () => {
    expect(studentFacingError(new Error('Network Error'))).toBeNull();
    expect(studentFacingError({})).toBeNull();
    expect(studentFacingError(undefined)).toBeNull();
  });
});

/**
 * A voice turn that fails must SAY so.
 *
 * The socket's `error` frame never reaches studentFacingError — it is not an
 * HTTP error — so it had no student-facing mapping at all. useWebSocket logged
 * it and stood the rescue watchdog down, and the turn ended in silence with the
 * status still reading "Listening…". A student who had just answered sat there
 * waiting for a reply that was never coming (reported 6 Aug).
 */
describe('a failed voice turn is announced, not swallowed', () => {
  it('always returns something to show — never empty', () => {
    for (const m of [undefined, '', 'Tutor unavailable', 'kaboom']) {
      expect(voiceTurnFailedMessage(m).trim().length).toBeGreaterThan(0);
    }
  });

  it('sends an expired session to sign in again', () => {
    expect(voiceTurnFailedMessage('INVALID_TOKEN: unauthorized')).toMatch(/signed in|log in/i);
  });

  it('names a slow tutor as the tutor being slow', () => {
    expect(voiceTurnFailedMessage('upstream timeout')).toMatch(/in time|too slow/i);
  });

  /**
   * "Tutor unavailable. Please try again." is the voice server's ONE catch-all
   * (streaming_server.py:689). It sends that same sentence whether the tutor
   * call timed out or came back 409/500 — any non-200 raises there.
   *
   * Reading "unavailable" as slowness therefore described a plain backend
   * rejection to the student as the tutor being slow, and to whoever read the
   * screenshot as a frontend timeout. That is exactly the wrong place to send
   * the next person looking (reported 7 Aug). Only wording that actually says
   * timeout gets the timeout copy.
   */
  it('does not report the server catch-all as slowness', () => {
    const msg = voiceTurnFailedMessage('Tutor unavailable. Please try again.');
    expect(msg).not.toMatch(/in time|too slow/i);
    expect(msg).toMatch(/try again|say it again/i);
  });

  it('never blames the student', () => {
    for (const m of ['Tutor unavailable', 'upstream timeout', 'INVALID_TOKEN']) {
      expect(voiceTurnFailedMessage(m)).not.toMatch(/you (got|were) (it )?wrong|your fault/i);
    }
  });

  it('does not leak the server string at the student', () => {
    expect(voiceTurnFailedMessage('NullPointerException at line 42')).not.toMatch(/NullPointer/);
  });
});

/**
 * Persisting the session id across reloads is what stops every refresh opening
 * a new session on a topic already in progress — the thing that produced 164
 * session starts and 16 SESSION_RESUMED on 7 Aug, each resumed session then
 * 500ing on every turn. The cost of keeping the id is that it can outlive the
 * backend, whose session state is in memory. Recognising that is what makes the
 * trade safe.
 */
describe('a session the backend has forgotten is recognised, not retried forever', () => {
  const err = (status: number, message?: string) => ({ response: { status, data: { message } } });

  it('spots the backend having dropped our session', () => {
    expect(isStaleSessionError(err(404, 'Session with ID SESSION123 was not found.'))).toBe(true);
  });

  it('does not treat every 404 as a dead session', () => {
    // A missing endpoint is not a missing session, and clearing the session id
    // for one would throw away a perfectly good lesson.
    expect(isStaleSessionError(err(404, 'Not Found'))).toBe(false);
  });

  it('leaves other failures alone', () => {
    expect(isStaleSessionError(err(500, 'Session blew up'))).toBe(false);
    expect(isStaleSessionError(err(409, 'Topic already in progress'))).toBe(false);
    expect(isStaleSessionError(new Error('Network Error'))).toBe(false);
    expect(isStaleSessionError(undefined)).toBe(false);
  });
});
