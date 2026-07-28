'use client';

/**
 * Log out — end the session and return to the login screen.
 *
 * There was no way to sign out at all: `useAuthStore.logout()` existed but
 * nothing called it, so switching accounts meant clearing site data in
 * devtools (asked for 2026-07-28).
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
import { LogOut } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { resetSessionStart } from '@/hooks/useDemoTutor';
import { stopTutorSpeech } from '@/lib/tts';
import { cn } from '@/lib/cn';

export default function LogOutButton({ className }: { className?: string }) {
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

  return (
    <>
      {/* Portalled to <body>. `position: fixed` is NOT relative to the viewport
          when an ancestor has a transform, filter or backdrop-filter — the tool
          rail uses .lg-glass-dark (backdrop-filter), which made this overlay
          lay out inside a 56px-wide nav instead of covering the screen
          (2026-07-28). A portal removes the ancestor entirely. */}
      {signingOut && mounted && createPortal(
        <div
          className="fixed inset-0 z-[100] bg-off-white flex flex-col items-center justify-center gap-4"
          role="status"
          aria-live="polite"
        >
          <span className="w-7 h-7 rounded-full border-2 border-muted-gray border-t-ai-cyan animate-spin-slow" />
          <span className="text-[13.5px] text-slate-blue">Signing out…</span>
        </div>,
        document.body,
      )}
    <button
      onClick={signOut}
      title="Log out"
      aria-label="Log out"
      className={cn(
        'w-9 h-9 rounded-lg flex items-center justify-center text-slate-blue hover:bg-reading-surface hover:text-ink transition-colors',
        className,
      )}
    >
      <LogOut size={17} strokeWidth={1.8} />
    </button>
    </>
  );
}
