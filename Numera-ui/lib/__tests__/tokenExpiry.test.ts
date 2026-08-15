/**
 * Scheduling the moment a login lapses.
 *
 * Every other input to the access decision arrives as a store change, which
 * renders the gate. Expiry arrives as nothing at all — the token goes stale
 * while the student sits on a page — so the gate has to wake itself. These
 * cover what that timer is told to wait for, including the two ways a naive
 * version breaks: a delay too large for setTimeout, and a zero delay that
 * re-arms itself forever.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { msUntilExpiry, isTokenValid } from '@/lib/auth/authApi';

/** A token with the given exp (seconds since epoch). Signature is irrelevant —
 *  nothing here verifies it; the server does that. */
function tokenWithExp(expSeconds: number | null): string {
  const claims = expSeconds === null ? { sub: 'u1' } : { sub: 'u1', exp: expSeconds };
  const b64 = (o: object) =>
    Buffer.from(JSON.stringify(o)).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `${b64({ alg: 'HS256' })}.${b64(claims)}.sig`;
}

afterEach(() => vi.useRealTimers());

describe('msUntilExpiry', () => {
  it('waits until a live token lapses', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-11T10:00:00Z'));
    const inOneHour = Math.floor(Date.parse('2026-08-11T11:00:00Z') / 1000);

    // One hour, less the 5s skew margin isTokenValid also applies — so the
    // re-check lands after the token is already treated as invalid.
    expect(msUntilExpiry(tokenWithExp(inOneHour))).toBe(3_600_000 - 5_000);
  });

  it('reports an already-lapsed token as zero, not a negative delay', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-11T10:00:00Z'));
    const anHourAgo = Math.floor(Date.parse('2026-08-11T09:00:00Z') / 1000);

    // The caller uses zero to mean "do not re-arm": accessDecision already has
    // the answer this render, and a zero-delay timer that re-arms itself spins.
    expect(msUntilExpiry(tokenWithExp(anHourAgo))).toBe(0);
    expect(isTokenValid(tokenWithExp(anHourAgo))).toBe(false);
  });

  it('caps a far-future expiry to something setTimeout can hold', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-11T10:00:00Z'));
    const inTenYears = Math.floor(Date.parse('2036-08-11T10:00:00Z') / 1000);

    // Past ~24.8 days setTimeout overflows its signed 32-bit delay and fires
    // immediately — which would spin the gate instead of sleeping.
    const wait = msUntilExpiry(tokenWithExp(inTenYears));
    expect(wait).toBe(2_147_483_647);
    expect(wait).toBeLessThanOrEqual(2 ** 31 - 1);
  });

  it('has nothing to schedule without a token or without an exp claim', () => {
    // A token with no exp cannot lapse on its own; the backend's 401 is what
    // ends that session, and a timer would fire on a promise nobody made.
    expect(msUntilExpiry(null)).toBeNull();
    expect(msUntilExpiry(undefined)).toBeNull();
    expect(msUntilExpiry('')).toBeNull();
    expect(msUntilExpiry(tokenWithExp(null))).toBeNull();
  });

  it('has nothing to schedule for a token it cannot read', () => {
    expect(msUntilExpiry('not-a-jwt')).toBeNull();
  });
});
