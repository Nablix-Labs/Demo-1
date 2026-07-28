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
import { basePath } from '@/lib/runtimeConfig';

// Routes that render on their own, without the tool rail or media panel.
const FOCUS_ROUTES = ['/onboard', '/diagnostic', '/orientation', '/teach', '/complete', '/consent', '/login', '/restricted'];

const ToolRail = dynamic(() => import('./ToolRail'), { ssr: false });
const MediaPanel = dynamic(() => import('./MediaPanel'), { ssr: false });
const VoicePicker = dynamic(() => import('./VoicePicker'), { ssr: false });
const LogOutButton = dynamic(() => import('./LogOutButton'), { ssr: false });

/**
 * A deployed build with no API base URL is a broken build, not mock mode.
 *
 * `NEXT_PUBLIC_*` are inlined at build time, so omitting NEXT_PUBLIC_API_BASE_URL
 * produces a bundle that compiles, deploys and loads — and then silently runs
 * the whole app on demo data, showing things like "2x + 5 = 13" as if they were
 * the student's real lesson. That shipped over a working build on 2026-07-28 and
 * read as the app being broken rather than as a bad deploy.
 *
 * basePath is only set for an exported build (EXPORT_BASE_PATH), so it is a
 * reliable "this is deployed, not local dev" signal. Local mock runs have
 * neither var and are unaffected.
 */
const misconfigured = Boolean(basePath) && !process.env.NEXT_PUBLIC_API_BASE_URL;

function ConfigError() {
  return (
    <div className="flex-1 flex items-center justify-center bg-off-white p-8">
      <div className="max-w-md text-center">
        <h1 className="text-[18px] font-semibold text-ink">This build can&apos;t reach the tutor</h1>
        <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">
          It was built without <code>NEXT_PUBLIC_API_BASE_URL</code>, so nothing here would be
          real — it would show demo content instead of your actual lesson.
        </p>
        <p className="text-[12px] text-slate-blue mt-3 leading-relaxed">
          Rebuild and redeploy using the command in <code>docs/DEPLOY.md</code>.
        </p>
      </div>
    </div>
  );
}

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

  if (misconfigured) return <ConfigError />;

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
        <div className="fixed bottom-5 left-5 z-50 flex items-center gap-1">
          <VoicePicker />
          <LogOutButton />
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
