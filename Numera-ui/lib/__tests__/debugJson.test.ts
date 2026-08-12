/**
 * The dev-only JSON viewer (Manjusha, 12 Aug 2026).
 *
 * Two properties matter more than any feature here. It must be INVISIBLE in a
 * production build — the payloads carry a real student's session — and it must
 * never be the thing that breaks the session it exists to observe, which means
 * no render path may throw on a payload however malformed.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  backendDebugObject,
  formatJson,
  redactForDisplay,
  toDebugCapture,
  debugJsonEnabled,
  recordDebugCall,
  getDebugCapture,
  clearDebugCapture,
  subscribeDebugCapture,
} from '@/lib/debugJson';

const setFlag = (value: string | undefined) => {
  if (value === undefined) delete process.env.NEXT_PUBLIC_DEBUG_JSON;
  else process.env.NEXT_PUBLIC_DEBUG_JSON = value;
};

describe('debug mode is off unless explicitly switched on', () => {
  afterEach(() => setFlag(undefined));

  it('is off when the flag is unset', () => {
    setFlag(undefined);
    expect(debugJsonEnabled()).toBe(false);
  });

  it('is off for anything other than the exact string "true"', () => {
    // A half-set flag must fail CLOSED: exposing a student's session because
    // someone wrote DEBUG_JSON=1 is the failure this guards.
    for (const value of ['1', 'yes', 'TRUE', 'false', '']) {
      setFlag(value);
      expect(debugJsonEnabled()).toBe(false);
    }
  });

  it('is on only for "true"', () => {
    setFlag('true');
    expect(debugJsonEnabled()).toBe(true);
  });
});

describe('capturing a call', () => {
  beforeEach(() => { clearDebugCapture(); setFlag('true'); });
  afterEach(() => { clearDebugCapture(); setFlag(undefined); });

  it('records nothing at all while debug mode is off', () => {
    setFlag(undefined);
    recordDebugCall('POST /interaction', { a: 1 }, { b: 2 });
    expect(getDebugCapture()).toBeNull();
  });

  it('keeps only the most recent call', () => {
    // Testers want "what did that click just send", not a history (spec §6).
    recordDebugCall('POST /interaction', { turn: 1 }, { ok: 1 });
    recordDebugCall('POST /canvas/submit', { turn: 2 }, { ok: 2 });
    expect(getDebugCapture()?.endpoint).toBe('POST /canvas/submit');
    expect(getDebugCapture()?.request).toEqual({ turn: 2 });
  });

  it('notifies subscribers so the panel re-renders', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeDebugCapture(listener);
    recordDebugCall('POST /interaction', {}, {});
    expect(listener).toHaveBeenCalled();
    unsubscribe();
    recordDebugCall('POST /interaction', {}, {});
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe("reading Chiru's debug object", () => {
  it('pulls out the Student Model pair when it is there', () => {
    const capture = toDebugCapture('POST /interaction', { q: 1 }, {
      message: 'hi',
      debug: { student_model_request: { a: 1 }, student_model_response: { b: 2 } },
    }, '13:00');
    expect(capture.studentModelRequest).toEqual({ a: 1 });
    expect(capture.studentModelResponse).toEqual({ b: 2 });
  });

  it('leaves the Student Model views empty when the backend sent no debug', () => {
    // The panel shows "Not provided by the backend" rather than an empty object,
    // so a tester can tell "Chiru has not shipped it" from "it was empty".
    const capture = toDebugCapture('POST /interaction', {}, { message: 'hi' }, '13:00');
    expect(capture.studentModelRequest).toBeUndefined();
    expect(formatJson(capture.studentModelRequest)).toBe('Not provided by the backend.');
  });

  it('is not fooled by a debug field that is not an object', () => {
    for (const debug of [null, 'yes', 42, undefined]) {
      expect(backendDebugObject({ debug })).toBeNull();
    }
    expect(backendDebugObject(null)).toBeNull();
    expect(backendDebugObject('not json')).toBeNull();
  });

  it('still captures the tutor payloads when there is no debug object', () => {
    // The whole reason the panel is useful before Chiru's side lands.
    const capture = toDebugCapture('POST /interaction', { turn_id: 'T-1' }, { message: 'hi' }, '13:00');
    expect(capture.request).toEqual({ turn_id: 'T-1' });
    expect(capture.response).toEqual({ message: 'hi' });
  });
});

describe('secrets never reach the screen', () => {
  it('redacts credentials wherever they are nested', () => {
    const out = redactForDisplay({
      access_token: 'ey.real.jwt',
      nested: { authorization: 'Bearer abc', password: 'hunter2' },
      list: [{ api_key: 'sk-live-123' }],
      student_id: 'ST009',
    }) as Record<string, never>;
    const text = JSON.stringify(out);
    for (const secret of ['ey.real.jwt', 'Bearer abc', 'hunter2', 'sk-live-123']) {
      expect(text).not.toContain(secret);
    }
    // Non-secrets must survive, or the panel is useless.
    expect(text).toContain('ST009');
  });

  it('matches a suffixed key without eating an unrelated one', () => {
    const out = redactForDisplay({ refresh_token: 'x', token_count: 7 }) as Record<string, unknown>;
    expect(out.refresh_token).toBe('[redacted]');
    expect(out.token_count).toBe(7);
  });
});

describe('rendering never throws', () => {
  it('survives a circular payload instead of taking the screen down', () => {
    const cyclic: Record<string, unknown> = { session_id: 'S1' };
    cyclic.self = cyclic;
    expect(() => formatJson(cyclic)).not.toThrow();
    expect(formatJson(cyclic)).toContain('[circular]');
  });

  it('renders the ordinary values a payload actually contains', () => {
    expect(formatJson({ a: null })).toContain('null');
    expect(formatJson([1, 2])).toContain('2');
    expect(formatJson('plain')).toBe('"plain"');
  });

  it('says so plainly when there is nothing to show', () => {
    expect(formatJson(undefined)).toBe('Not provided by the backend.');
  });
});
