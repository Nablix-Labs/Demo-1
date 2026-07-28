'use client';

/**
 * AppFrame — decides which app chrome wraps the routed page.
 *
 * The tool rail + AI media panel are part of the live tutoring experience, so
 * they only belong to the in-lesson routes. The pre-lesson flows (onboarding,
 * diagnostics, orientation video) render full-bleed with no chrome.
 */

import { useEffect, type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { usePathname } from 'next/navigation';
import AuthGate from './auth/AuthGate';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import { usePhaseRouting } from '@/lib/usePhaseRouting';

// Routes that render on their own, without the tool rail or media panel.
const FOCUS_ROUTES = ['/onboard', '/diagnostic', '/orientation', '/teach', '/complete', '/consent', '/login', '/restricted'];

const ToolRail = dynamic(() => import('./ToolRail'), { ssr: false });
const MediaPanel = dynamic(() => import('./MediaPanel'), { ssr: false });
const VoicePicker = dynamic(() => import('./VoicePicker'), { ssr: false });

export default function AppFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const panelSide = useNumeraStore((s) => s.panelSide);

  // Follow the backend's phase across the flow (no-op until a phase advances).
  usePhaseRouting();

  // Load persisted UI prefs + progress once, on the client only.
  useEffect(() => {
    void useNumeraStore.persist.rehydrate();
  }, []);

  // Testing-only student identity override: /app/?student=ST008
  //
  // The tutoring API needs the student's own ST### code, but /auth/login does
  // not return one yet (see LoginResponse.student_code), so every logged-in
  // student falls back to ST001 and student_model answers
  // 403 STUDENT_FORBIDDEN — "student_code does not belong to the authenticated
  // user". This lets a tester pin their real code until the backend sends it.
  // A code from a real login always wins; delete this with the fallback.
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get('student');
    if (code && /^ST\d+$/i.test(code)) {
      void useAuthStore.persist.rehydrate();
      useAuthStore.getState().setStudentCode(code.toUpperCase());
      console.warn(`[auth] student code pinned to ${code.toUpperCase()} via ?student= (testing override)`);
    }
  }, []);

  const focus = FOCUS_ROUTES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (focus) {
    // Full-bleed: just the routed page — plus the voice picker, which otherwise
    // only mounts inside MediaPanel on the lesson route. Since routing follows
    // the backend phase, a tester now spends most of their time on diagnostic /
    // orientation / teach and could never reach the picker at all.
    return (
      <div className="flex-1 flex min-w-0 relative">
        {children}
        <div className="fixed bottom-5 left-5 z-50">
          <VoicePicker />
        </div>
      </div>
    );
  }

  // The AI tutor panel belongs to the live lesson only; every other in-app
  // route keeps the tool rail for navigation but renders content full-width.
  const isLesson = pathname === '/';

  return (
    <AuthGate>
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
    </AuthGate>
  );
}
