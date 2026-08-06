'use client';

/**
 * Log out — the button form, for the routes that have no dock.
 *
 * The dock carries its own Log out tile, so the sign-out sequence itself lives
 * in useSignOut(); this is just the affordance.
 */

import { LogOut } from 'lucide-react';
import { useSignOut } from '@/hooks/useSignOut';
import { cn } from '@/lib/cn';

export default function LogOutButton({ className }: { className?: string }) {
  const { signOut, overlay } = useSignOut();

  return (
    <>
      {overlay}
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
