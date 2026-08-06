'use client';

/**
 * /dev-screens — every screen in the app, live, on one page.
 *
 * A contact sheet of the real running app rather than a set of screenshots: each
 * tile is an iframe of the actual route, so a UI change shows up across all of
 * them at once and drift between screens is visible without clicking through
 * twenty-three of them. Screenshots go stale the moment we edit; this does not.
 *
 * Dev-only. It is listed in FOCUS_ROUTES and PRE_AUTH_ROUTES so it renders bare —
 * no tool rail, no AuthGate, no floating voice picker over the tiles.
 *
 * The tiles are scaled with `transform: scale()` on a full-size viewport rather
 * than a small iframe, because the app is responsive: a 380px-wide iframe renders
 * the MOBILE layout, which is not what we are checking when we look at a desktop
 * grid. Each frame is laid out at its true width and shrunk optically.
 */

import { useEffect, useRef, useState } from 'react';
import {
  useAuthStore,
  ACCOUNT_BLOCKING_PURPOSES,
  accessDecision,
} from '@/store/useAuthStore';

interface Screen {
  path: string;
  label: string;
  group: string;
}

// Every page.tsx under app/, with the three dynamic routes given a real topic so
// they render content instead of a param placeholder.
const SCREENS: Screen[] = [
  { path: '/login', label: 'Login', group: 'Pre-auth' },
  { path: '/onboard', label: 'Onboard', group: 'Pre-auth' },
  { path: '/consent', label: 'Consent', group: 'Pre-auth' },
  { path: '/consent/manage', label: 'Consent — manage', group: 'Pre-auth' },
  { path: '/restricted', label: 'Restricted', group: 'Pre-auth' },

  { path: '/diagnostic', label: 'Diagnostic — picker', group: 'Learning flow' },
  { path: '/diagnostic/statistics', label: 'Diagnostic — topic', group: 'Learning flow' },
  { path: '/orientation/statistics', label: 'Orientation', group: 'Learning flow' },
  { path: '/teach/statistics', label: 'Teach back', group: 'Learning flow' },
  { path: '/', label: 'Guided lesson', group: 'Learning flow' },
  { path: '/practice', label: 'Independent practice', group: 'Learning flow' },
  { path: '/review', label: 'Review', group: 'Learning flow' },
  { path: '/complete', label: 'Complete', group: 'Learning flow' },
  { path: '/challenge', label: 'Challenge', group: 'Learning flow' },

  { path: '/workbook', label: 'Workbook', group: 'Library' },
  { path: '/workbook/statistics', label: 'Workbook — topic', group: 'Library' },
  { path: '/keynotes', label: 'Key notes', group: 'Library' },
  { path: '/history', label: 'History', group: 'Library' },
  { path: '/files', label: 'Files', group: 'Library' },
  { path: '/people', label: 'People', group: 'Library' },
  { path: '/notifications', label: 'Notifications', group: 'Library' },
  { path: '/help', label: 'Help', group: 'Library' },
  { path: '/flagged', label: 'Flagged', group: 'Library' },
];

const VIEWPORTS = {
  desktop: { w: 1512, h: 900, label: 'Desktop 1512×900' },
  mobile: { w: 390, h: 780, label: 'Mobile 390×780' },
} as const;

type ViewportKey = keyof typeof VIEWPORTS;

export default function ScreensPage() {
  const [viewport, setViewport] = useState<ViewportKey>('desktop');

  /**
   * Tiles mount lazily, and "load all" mounts them ONE AT A TIME.
   *
   * Two separate reasons, both observed rather than guessed:
   *
   * 1. Mounting all twenty-three at once makes `next dev` compile twenty-three
   *    routes concurrently, and it loses that race — it returns 500s with
   *    `SyntaxError: Unexpected non-whitespace character after JSON` from its own
   *    build manifest. Verified on a freshly cleared `.next`, so it is the
   *    concurrency, not a stale cache: the routes that compiled first returned
   *    200 and the failures began only once many were in flight together.
   * 2. The app runs several WebGL contexts (background shader, 3D avatar); a
   *    browser evicts the oldest when too many exist, and an evicted canvas keeps
   *    its last pixels and ignores every draw — the defect f0c85cd fixed.
   *
   * `revealed` is the number of tiles allowed to mount so far.
   */
  const [revealed, setRevealed] = useState(0);
  const [running, setRunning] = useState(false);
  const stall = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Strictly sequential: the next tile mounts only once the previous iframe has
   * fired `load`. A fixed delay is not enough — a cold `next dev` route compile
   * measured 22–44s here, so any interval short enough to be usable still stacks
   * compiles and loses the manifest race.
   */
  const advance = () => {
    if (stall.current) clearTimeout(stall.current);
    setRevealed((n) => {
      const next = Math.min(n + 1, SCREENS.length);
      if (next === SCREENS.length) setRunning(false);
      return next;
    });
  };

  const loadAll = () => {
    if (running || revealed > 0) {
      if (stall.current) clearTimeout(stall.current);
      setRunning(false);
      setRevealed(0);
      return;
    }
    setRunning(true);
    setRevealed(1);
  };

  // A route that 500s never fires a useful load event on some browsers; don't
  // let one bad tile stall the remaining twenty-two.
  useEffect(() => {
    if (!running || revealed === 0 || revealed >= SCREENS.length) return;
    stall.current = setTimeout(advance, 60_000);
    return () => {
      if (stall.current) clearTimeout(stall.current);
    };
  }, [running, revealed]);

  /**
   * Mock sign-in, so the gated screens show themselves instead of /login.
   *
   * Thirteen of the twenty-three routes sit behind AuthGate, and with no signed-in
   * student every one of them renders the login screen — the grid showed /workbook,
   * /history, /people, the guided lesson and nine others as thirteen identical
   * copies of "Welcome back". The iframes are same-origin, so seeding the
   * persisted auth store here is enough for all of them.
   *
   * This drives the store's own actions rather than hand-writing the persisted
   * JSON: the shape of `numera-auth` is the store's business, and a hand-rolled
   * blob would rot the moment it changes. Nothing here touches a real token —
   * `accessDecision` falls through to the mock chain only when accessToken is
   * null, which is exactly the local no-backend case.
   */
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    void useAuthStore.persist.rehydrate();
    setSignedIn(accessDecision(useAuthStore.getState()).allowed);
  }, []);

  const mockSignIn = () => {
    const s = useAuthStore.getState();
    if (signedIn) {
      s.logout();
      setSignedIn(false);
      return;
    }
    s.acceptConsents(ACCOUNT_BLOCKING_PURPOSES);
    s.acknowledgeDisclosure();
    s.activateAccount();
    useAuthStore.setState({ role: 'student' });
    setSignedIn(accessDecision(useAuthStore.getState()).allowed);
  };

  const vp = VIEWPORTS[viewport];
  const tileWidth = 440;
  const scale = tileWidth / vp.w;

  const groups = [...new Set(SCREENS.map((s) => s.group))];

  return (
    <div className="w-full h-screen overflow-auto bg-[#EEF1F6] text-ink">
      <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-muted-gray px-6 py-3 flex items-center gap-4">
        <div>
          <h1 className="text-[17px] font-semibold">Numera — all screens</h1>
          <p className="text-[12px] text-slate-blue">
            {SCREENS.length} routes, live. Mock data — no API base URL set.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {(Object.keys(VIEWPORTS) as ViewportKey[]).map((k) => (
            <button
              key={k}
              onClick={() => setViewport(k)}
              className={`px-3 py-1.5 rounded-md text-[12px] border transition-colors ${
                viewport === k
                  ? 'bg-ink text-white border-ink'
                  : 'bg-white border-muted-gray hover:border-ink'
              }`}
            >
              {VIEWPORTS[k].label}
            </button>
          ))}
          <button
            onClick={mockSignIn}
            className={`px-3 py-1.5 rounded-md text-[12px] border transition-colors ${
              signedIn
                ? 'bg-ai-cyan text-ink border-ai-cyan'
                : 'bg-white border-muted-gray hover:border-ink'
            }`}
          >
            {signedIn ? 'Signed in (mock)' : 'Sign in (mock)'}
          </button>
          <button
            onClick={loadAll}
            className="px-3 py-1.5 rounded-md text-[12px] border border-muted-gray bg-white hover:border-ink"
          >
            {revealed > 0
              ? `Unload frames (${Math.min(revealed, SCREENS.length)}/${SCREENS.length})`
              : 'Load all frames'}
          </button>
        </div>
      </header>

      <div className="px-6 pb-16">
        {groups.map((group) => (
          <section key={group}>
            <h2 className="mt-8 mb-3 text-[13px] font-semibold uppercase tracking-wide text-slate-blue">
              {group}
            </h2>
            <div className="flex flex-wrap gap-5">
              {SCREENS.filter((s) => s.group === group).map((s) => (
                <Tile
                  key={s.path}
                  screen={s}
                  width={tileWidth}
                  vw={vp.w}
                  vh={vp.h}
                  scale={scale}
                  // Index into the flat SCREENS order, so the stagger reveals
                  // tiles in the order they are listed rather than per section.
                  live={SCREENS.indexOf(s) < revealed}
                  onLoaded={
                    running && SCREENS.indexOf(s) === revealed - 1
                      ? advance
                      : undefined
                  }
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function Tile({
  screen,
  width,
  vw,
  vh,
  scale,
  live,
  onLoaded,
}: {
  screen: Screen;
  width: number;
  vw: number;
  vh: number;
  scale: number;
  live: boolean;
  onLoaded?: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const show = live || loaded;

  return (
    <figure className="m-0" style={{ width }}>
      <div
        className="relative overflow-hidden rounded-xl border border-muted-gray bg-white shadow-sm"
        style={{ width, height: vh * scale }}
      >
        {show ? (
          <iframe
            src={screen.path}
            title={screen.label}
            width={vw}
            height={vh}
            onLoad={onLoaded}
            className="border-0 origin-top-left"
            style={{ transform: `scale(${scale})` }}
          />
        ) : (
          <button
            onClick={() => setLoaded(true)}
            className="w-full h-full flex items-center justify-center text-[12px] text-slate-blue hover:bg-slate-50"
          >
            Load
          </button>
        )}
      </div>
      <figcaption className="mt-2 flex items-baseline gap-2">
        <a
          href={screen.path}
          target="_blank"
          rel="noreferrer"
          className="text-[13px] font-medium hover:underline"
        >
          {screen.label}
        </a>
        <code className="text-[11px] text-slate-blue">{screen.path}</code>
      </figcaption>
    </figure>
  );
}
