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

import { useRouter } from 'next/navigation';
import { LogOut } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { resetSessionStart } from '@/hooks/useDemoTutor';
import { stopTutorSpeech } from '@/lib/tts';
import { cn } from '@/lib/cn';

export default function LogOutButton({ className }: { className?: string }) {
  const router = useRouter();

  const signOut = () => {
    stopTutorSpeech();
    resetSessionStart();
    useNumeraStore.getState().reset();
    useAuthStore.getState().logout();
    router.replace('/login');
  };

  return (
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
  );
}
