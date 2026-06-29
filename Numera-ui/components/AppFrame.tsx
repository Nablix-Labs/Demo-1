'use client';

/**
 * AppFrame — decides which app chrome wraps the routed page.
 *
 * The tool rail + AI media panel are part of the live tutoring experience, so
 * they only belong to the in-lesson routes. The pre-lesson flows (onboarding,
 * diagnostics, orientation video) render full-bleed with no chrome.
 */

import { useEffect, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import ToolRail from './ToolRail';
import MediaPanel from './MediaPanel';
import { useNumeraStore } from '@/store/useNumeraStore';

// Routes that render on their own, without the tool rail or media panel.
const FOCUS_ROUTES = ['/onboard', '/diagnostic', '/orientation', '/complete'];

export default function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const panelSide = useNumeraStore((s) => s.panelSide);

  // Load persisted UI prefs + progress once, on the client only.
  useEffect(() => {
    void useNumeraStore.persist.rehydrate();
  }, []);

  const focus = FOCUS_ROUTES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (focus) {
    // Full-bleed: just the routed page.
    return <div className="flex-1 flex min-w-0">{children}</div>;
  }

  // The AI tutor panel belongs to the live lesson only; every other in-app
  // route keeps the tool rail for navigation but renders content full-width.
  const isLesson = pathname === '/';

  return (
    <>
      <ToolRail />
      <div className="flex-1 flex min-w-0">
        {!isLesson ? (
          children
        ) : panelSide === 'left' ? (
          <>
            <MediaPanel />
            {children}
          </>
        ) : (
          <>
            {children}
            <MediaPanel />
          </>
        )}
      </div>
    </>
  );
}
