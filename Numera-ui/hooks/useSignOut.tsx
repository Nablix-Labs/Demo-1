'use client';

/**
 * Sign-out — end the session and return to the login screen.
 *
 * Extracted from LogOutButton when the dock landed: Log out is a tile in the
 * dock and still a button on the routes that have no dock, and the ordering
 * below is too easy to get wrong to have two copies of it.
 *
 * Clearing the token is not enough. Everything below survives a logout
 * otherwise, and the next person to sign in inherits it:
 *   - the tutoring session id and backend record, so their first call would
 *     run against someone else's session
 *   - the flow progress (`phasesDone`, topic, phase) that drives routing
 *   - the module-level session-start latch in useDemoTutor, which would
 *     refuse to open a session for the new student
 *   - any tutor speech still playing
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { resetSessionStart } from '@/hooks/useDemoTutor';
import { stopTutorSpeech } from '@/lib/tts';

export function useSignOut() {
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [mounted, setMounted] = useState(false); // portals need a client DOM
  useEffect(() => setMounted(true), []);

  /**
   * Order matters here.
   *
   * Clearing the stores first re-rendered whatever screen the student was on
   * with its data gone — the diagnostic blanked its own question — and only
   * then navigated. It read as the app breaking on the way out (reported with
   * a screen recording, 2026-07-28).
   *
   * So: cover the screen, navigate, and only wipe state once the route has
   * actually changed. Nothing ever renders a half-cleared screen.
   */
  const signOut = () => {
    if (signingOut) return;
    setSigningOut(true);
    stopTutorSpeech();
    router.replace('/login');
    // After the route swap, so the screen being left is never re-rendered empty.
    setTimeout(() => {
      resetSessionStart();
      useNumeraStore.getState().reset();
      useAuthStore.getState().logout();
    }, 0);
  };

  /* Portalled to <body>. `position: fixed` is NOT relative to the viewport
     when an ancestor has a transform, filter or backdrop-filter — the tool
     rail used .lg-glass-dark (backdrop-filter), which made this overlay lay
     out inside a 56px-wide nav instead of covering the screen (2026-07-28).
     The dock uses the same material, so the portal still earns its keep. */
  const overlay =
    signingOut && mounted
      ? createPortal(
          <div
            className="fixed inset-0 z-[100] bg-off-white flex flex-col items-center justify-center gap-4"
            role="status"
            aria-live="polite"
          >
            <span className="w-7 h-7 rounded-full border-2 border-muted-gray border-t-ai-cyan animate-spin-slow" />
            <span className="text-[13.5px] text-slate-blue">Signing out…</span>
          </div>,
          document.body,
        )
      : null;

  return { signOut, signingOut, overlay };
}
