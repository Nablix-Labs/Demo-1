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

export default function AuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    void useAuthStore.persist.rehydrate();
    return useAuthStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  const state = useAuthStore();
  const outcome = accessDecision(state);

  useEffect(() => {
    if (!hydrated) return;
    if (state.role === null) { router.replace('/onboard'); return; }
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
