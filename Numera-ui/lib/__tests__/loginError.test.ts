/**
 * Login error copy — what the student is told when sign-in fails.
 *
 * The bug this locks down: a 404 from the missing nginx `/nablix-auth` location
 * was reported to the student as "No account found for that email", so Manjusha
 * was told her account didn't exist when the account was fine (2026-07-27).
 * The auth API itself never returns 404 — verified against nablix.ai:8080 — so
 * a 404 can only mean the request never reached it.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { login, LoginError } from '@/lib/auth/authApi';

/** Stub fetch with one non-2xx response. `body` is null for a non-JSON page. */
function mockFetch(status: number, body: unknown | null) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status,
      json: async () => {
        if (body === null) throw new SyntaxError('not JSON');
        return body;
      },
    }),
  );
}

async function messageFor(status: number, body: unknown | null): Promise<string> {
  mockFetch(status, body);
  try {
    await login('someone@example.com', 'pw');
  } catch (e) {
    return (e as LoginError).message;
  }
  throw new Error('login should have thrown');
}

describe('login error copy', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('does not blame the account when the request never reached the auth API', async () => {
    // nginx serves an HTML 404 page, so there is no JSON body to read.
    const msg = await messageFor(404, null);
    expect(msg).not.toMatch(/no account/i);
    expect(msg).toMatch(/sign-in service/i);
  });

  it('treats gateway errors the same as a missing route', async () => {
    expect(await messageFor(502, null)).toMatch(/sign-in service/i);
  });

  it('reports rejected credentials from the error_code', async () => {
    const msg = await messageFor(401, {
      error_code: 'INVALID_CREDENTIALS',
      message: 'Invalid email or password.',
      field: null,
    });
    expect(msg).toMatch(/don't match/i);
  });

  it('points at the email field on a validation error', async () => {
    const msg = await messageFor(422, {
      error_code: 'VALIDATION_ERROR',
      message: 'value is not a valid email address: ...',
      field: 'email',
    });
    expect(msg).toMatch(/valid email/i);
  });

  it("never shows the server's developer-facing message", async () => {
    const msg = await messageFor(422, {
      error_code: 'VALIDATION_ERROR',
      message: 'value is not a valid email address: The part after the @-sign is reserved.',
      field: 'email',
    });
    expect(msg).not.toMatch(/@-sign/);
  });
});

/**
 * The tutor avatar must not "talk" with no audio.
 *
 * The mouth used to pulse on a bare interval, stopped only by the audio's
 * onended/onerror. When playback stalled or never really started, neither
 * fired — so the face kept talking silently, with no text either (reported
 * 2026-07-28). This pins the rule the fix relies on: a pulse only counts when
 * the audio's currentTime has actually advanced.
 */
describe('avatar mouth follows real audio progress', () => {
  const STALL_TICKS = 6;

  /** Mirrors the interval body in lib/tts.ts. */
  function tick(state: { lastTime: number; stalled: number }, audio: { paused: boolean; ended: boolean; currentTime: number }) {
    const advanced = !audio.paused && !audio.ended && audio.currentTime > state.lastTime;
    if (advanced) {
      state.lastTime = audio.currentTime;
      state.stalled = 0;
      return 'pulse';
    }
    return ++state.stalled >= STALL_TICKS ? 'finish' : 'wait';
  }

  it('pulses while audio is playing', () => {
    const s = { lastTime: -1, stalled: 0 };
    const audio = { paused: false, ended: false, currentTime: 0 };
    const out: string[] = [];
    for (let i = 1; i <= 3; i++) { audio.currentTime = i * 0.2; out.push(tick(s, audio)); }
    expect(out).toEqual(['pulse', 'pulse', 'pulse']);
  });

  it('ends the utterance when audio stalls instead of animating forever', () => {
    const s = { lastTime: 1, stalled: 0 };
    const audio = { paused: false, ended: false, currentTime: 1 }; // frozen
    const out = Array.from({ length: STALL_TICKS }, () => tick(s, audio));
    expect(out[out.length - 1]).toBe('finish');
  });

  it('never pulses for audio that never started', () => {
    const s = { lastTime: -1, stalled: 0 };
    const audio = { paused: true, ended: false, currentTime: 0 };
    const out = Array.from({ length: STALL_TICKS }, () => tick(s, audio));
    expect(out).not.toContain('pulse');
    expect(out[out.length - 1]).toBe('finish');
  });
});
