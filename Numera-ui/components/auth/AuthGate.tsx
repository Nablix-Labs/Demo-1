'use client';

/**
 * AuthGate — client-side RBAC enforcement (§13) for in-app routes. Runs the
 * access-decision chain and redirects blocked users to /login, /consent or
 * /restricted. Waits for the persisted auth store to hydrate first, so a valid
 * student isn't bounced on refresh.
 *
 * This mirrors the backend rule: the frontend may hide features, but access is
 * decided by role + account_status + consent — never by visibility alone.
 */

import { useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, accessDecision } from '@/store/useAuthStore';
import { msUntilExpiry } from '@/lib/auth/authApi';

export default function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    void useAuthStore.persist.rehydrate();
    setHydrated(true);
  }, []);

  const state = useAuthStore();
  // The decision is recomputed on render, and every other input to it changes
  // the store — so a render is guaranteed. Expiry is the exception: it happens
  // to a token nobody touched, on a screen nobody navigated away from. This
  // wakes the gate at that moment so the lapse is acted on instead of waiting
  // for the student's next click (Manjusha, 11 Aug).
  const [expiryCheck, setExpiryCheck] = useState(0);
  useEffect(() => {
    const wait = msUntilExpiry(state.accessToken);
    // Nothing to wait for (no token / no exp), or it has already lapsed — in
    // which case accessDecision has the answer this render and re-arming a
    // zero-delay timer would spin.
    if (wait === null || wait === 0) return;
    const id = setTimeout(() => setExpiryCheck((n) => n + 1), wait);
    return () => clearTimeout(id);
    // `expiryCheck` is a dependency so each wake re-arms: msUntilExpiry caps at
    // ~24.8 days, so a longer-lived token needs more than one sleep.
  }, [state.accessToken, expiryCheck]);

  const outcome = accessDecision(state);

  useEffect(() => {
    if (!hydrated) return;
    // No role means nobody is signed in — which is true both for a first-time
    // visitor AND for someone who just signed out, and the two are
    // indistinguishable from state. Send them to /login, which links to
    // sign-up; sending them to /onboard dropped a returning student who had
    // just logged out into account creation (2026-07-28).
    if (state.role === null) { router.replace('/login'); return; }
    if (!outcome.allowed) router.replace(outcome.redirect);
  }, [hydrated, state.role, outcome, router]);

  // Hold the render until we know access is allowed (avoids a flash of the app).
  if (!hydrated || state.role === null || !outcome.allowed) {
    return (
      <div className="flex-1 flex items-center justify-center bg-white" aria-busy="true" aria-label="Checking access">
        <span className="w-6 h-6 rounded-full border-2 border-muted-gray border-t-ai-cyan animate-spin-slow" />
      </div>
    );
  }

  return <>{children}</>;
}
