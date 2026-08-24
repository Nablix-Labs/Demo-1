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
import { cn } from '@/lib/cn';
import AuthGate from './auth/AuthGate';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import { usePhaseRouting } from '@/lib/usePhaseRouting';
import { basePath } from '@/lib/runtimeConfig';

// Routes that render on their own, without the tool rail or media panel.
// Screens shown before a student is signed in.
const PRE_AUTH_ROUTES = ['/login', '/onboard', '/consent', '/restricted', '/dev-screens'];

const FOCUS_ROUTES = ['/onboard', '/diagnostic', '/orientation', '/teach', '/complete', '/consent', '/login', '/restricted', '/dev-screens'];

/**
 * Routes where a lesson is actually in progress.
 *
 * The dock is hidden here. Not for tidiness — it does not work. Routing
 * follows the backend's current_phase and usePhaseRouting re-asserts it on every
 * path change, so a student who clicks Workbook mid-lesson is pushed back to the
 * lesson within a second. Verified live on 2026-07-29: Workbook, Key Notes and
 * History all bounced straight back to `/`.
 *
 * Eleven controls that visibly do nothing are worse than no controls, so the
 * dock now appears only where a student can genuinely go somewhere — between
 * lessons, on the library screens. The learning flow is a flow; the dock is for
 * the places either side of it.
 */
const TUTORING_ROUTES = ['/', '/practice'];

/**
 * Does this pathname sit on the given route?
 *
 * Shared because the export build sets `trailingSlash: true`, so every route
 * but `/` arrives here with a trailing slash — `usePathname()` returns
 * `/practice/`, never `/practice`. Two of the three checks below already
 * allowed for that; `tutoring` compared with bare `===` and so was false on
 * every deployed build.
 *
 * The cost was not cosmetic. `tutoring` is what auto-hides the dock, so on the
 * live site the dock sat permanently across the bottom of Independent Practice,
 * covering the canvas toolbar — pen, eraser, shapes, undo, colour and the Check
 * button that submits the work. The student could see their canvas and not
 * reach any of the controls for it.
 *
 * It never reproduced locally: `trailingSlash` is set only for the static
 * export, so `npm run dev` matches `/practice` exactly and the dock behaves.
 * One matcher now, so the three lists cannot drift apart again.
 */
function matchesRoute(pathname: string, route: string): boolean {
  return pathname === route || pathname.startsWith(`${route}/`);
}

const Dock = dynamic(() => import('./Dock'), { ssr: false });
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
  const panelWidth = useNumeraStore((s) => s.panelWidth);
  const panelCollapsed = useNumeraStore((s) => s.panelCollapsed);

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

  const focus = FOCUS_ROUTES.some((p) => matchesRoute(pathname, p));

  // Pre-auth screens: nobody is signed in, so a Log out button and a tutor
  // voice picker are nonsense there — the logout icon showed up on /login
  // itself after signing out.
  const preAuth = PRE_AUTH_ROUTES.some((p) => matchesRoute(pathname, p));

  if (focus) {
    // Full-bleed: just the routed page — plus the voice picker, which otherwise
    // only mounts inside MediaPanel on the lesson route. Since routing follows
    // the backend phase, a tester now spends most of their time on diagnostic /
    // orientation / teach and could never reach the picker at all.
    const page = (
      <div className="flex-1 flex min-w-0 relative">
        {children}
        {!preAuth && (
          <div className="fixed bottom-5 left-5 z-50 flex items-center gap-1">
            <VoicePicker />
            <LogOutButton />
          </div>
        )}
      </div>
    );
    // Focus mode is a LAYOUT choice, not an access one. Returning the page bare
    // meant /diagnostic, /orientation, /teach and /complete ran the access
    // decision never — and since routing follows the backend phase, that is
    // where a student spends most of the lesson. An expired login stayed on
    // screen indefinitely there (Manjusha, 11 Aug).
    //
    // The pre-auth screens must stay outside the gate: they are where someone
    // with no session is meant to land, and gating /login would bounce them to
    // /login.
    return preAuth ? page : <AuthGate>{page}</AuthGate>;
  }

  // The AI tutor panel belongs to the live lesson only; every other in-app
  // route keeps the tool rail for navigation but renders content full-width.
  const isLesson = pathname === '/';
  const tutoring = TUTORING_ROUTES.some((p) => matchesRoute(pathname, p));

  return (
    <AuthGate>
      {/* Tucked away on the lesson routes rather than absent. The lesson gets
          its full width and the canvas keeps bottom-centre, but pushing the
          pointer to the bottom edge always brings navigation back — so
          tapping Lesson from the Workbook is no longer a one-way door. */}
      <Dock autoHide={tutoring} />
      {/* The dock is hidden on the tutoring routes so the lesson gets the
          full screen — but those are not FOCUS_ROUTES either, so they were the
          only screens in the app with no way out. A student in guided or
          independent practice could not sign out at all (Manjusha, 4 Aug).
          Same cluster and same corner as focus mode, so it is where anyone who
          has used the rest of the app already expects it. Bottom-left is clear
          on both: the canvas toolbar docks bottom-centre and the FABs and
          action row sit bottom-right. */}
      {/* Log out only — no VoicePicker here. MediaPanel already mounts one on
          the lesson route, and a second would be two controls writing the same
          store field from opposite corners of the same screen. */}
      {/* Clear of the tutor panel, not on top of it.
          bottom-left was chosen when nothing else lived there. The MediaPanel
          now sits on that side with its message box at the bottom, so this
          cluster landed directly on the composer — measured live on the VM:
          logout at x20 y805, composer at x15 y806, overlapping. It shifts past
          whichever edge the panel is docked to. */}
      {tutoring && (
        <div
          className="fixed bottom-5 z-50 flex items-center gap-1"
          // Follows the panel now that its width is draggable. This was
          // `left-[250px]`, hardcoded off the old fixed 234 — widening the
          // panel used to slide it back underneath the composer, which is the
          // overlap the comment above was written about in the first place.
          style={{ left: panelSide === 'left' ? (panelCollapsed ? 28 : panelWidth) + 16 : 20 }}
        >
          {!isLesson && <VoicePicker />}
          <LogOutButton />
        </div>
      )}
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
