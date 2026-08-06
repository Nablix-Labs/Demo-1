import { describe, it, expect } from 'vitest';
import { studentFacingError } from '@/lib/api';

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

  it('a 502 carries the backend explanation when there is one', () => {
    expect(studentFacingError(err(502, { message: 'student_model rejected request' })))
      .toContain('student_model rejected request');
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
    // The ALG_1STEP_GP_F01 lesson: a confident wrong explanation sent the team
    // looking in the wrong place for two days.
    const msg = studentFacingError(
      err(409, { message: 'Student Model did not return metadata for ALG_1STEP_GP_F01' }),
    );
    expect(msg).not.toMatch(/already have this topic/i);
    expect(msg).toContain('ALG_1STEP_GP_F01');
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
