'use client';

/**
 * Dock — app navigation, replacing the vertical tool rail.
 *
 * Practice is deliberately absent: it is a PHASE, not a place. The backend
 * decides when a student is in independent practice, so offering it as a
 * destination promised something the student could never choose.
 *
 * Where the dock appears is decided in AppFrame, and the rules are unchanged
 * from the rail: it is hidden on the tutoring routes, because usePhaseRouting
 * re-asserts the backend's current_phase on every path change and a student who
 * clicks Workbook mid-lesson is pushed back within a second.
 */

import { useMemo, useState } from 'react';
import { usePathname } from 'next/navigation';
import MacOSDock, { type DockApp } from '@/components/ui/mac-os-dock';
import { cn } from '@/lib/cn';
import {
  LessonIcon, WorkbookIcon, ChallengeIcon, KeyNotesIcon, PeopleIcon,
  FilesIcon, FlaggedIcon, NotificationsIcon, HistoryIcon, HelpIcon, ProfileIcon,
  LogOutIcon,
} from '@/components/ui/dock-icons';
import { useSignOut } from '@/hooks/useSignOut';

/**
 * Module scope, not a hook body. `apps` is a dependency of the dock's
 * magnification and layout effects, so a fresh array each render would reset
 * icon positions to their unmagnified values on every frame.
 */
const APPS: DockApp[] = [
  { id: 'lesson',        name: 'Lesson',          href: '/',              icon: LessonIcon },
  { id: 'workbook',      name: 'Workbook',        href: '/workbook',      icon: WorkbookIcon },
  { id: 'challenge',     name: 'Group Challenge', href: '/challenge',     icon: ChallengeIcon },
  { id: 'keynotes',      name: 'Key Notes',       href: '/keynotes',      icon: KeyNotesIcon },
  { id: 'people',        name: 'People',          href: '/people',        icon: PeopleIcon },
  { id: 'files',         name: 'Files',           href: '/files',         icon: FilesIcon },
  { id: 'flagged',       name: 'Flagged',         href: '/flagged',       icon: FlaggedIcon },
  { id: 'notifications', name: 'Notifications',   href: '/notifications', icon: NotificationsIcon },
  { id: 'history',       name: 'History',         href: '/history',       icon: HistoryIcon },
  { id: 'help',          name: 'Help & support',  href: '/help',          icon: HelpIcon },
  { id: 'profile',       name: 'Profile',         href: '/profile',       icon: ProfileIcon },
  // No href — this one acts rather than navigates, so it comes back through
  // onAppClick below. Last in the row on purpose; see the note on LogOutIcon.
  { id: 'logout',        name: 'Log out',                                 icon: LogOutIcon },
];

/**
 * `autoHide` — the dock tucks off-screen and slides up when the pointer reaches
 * the bottom edge, exactly as macOS does.
 *
 * Used on the lesson routes, and it is not decoration. usePhaseRouting pushes
 * the student back to the lesson from anywhere while a phase is live, so the
 * lesson used to be a one-way door: tapping Lesson from the Workbook landed you
 * on a screen with no navigation at all and no way back to the library. A dock
 * that is present-but-tucked means no screen in the app is ever a dead end,
 * while still leaving the canvas its full width and the toolbar its space at
 * bottom-centre.
 *
 * The tiles that the backend will bounce still bounce — that is the backend's
 * call, not something the frontend can honestly paper over — but "I can get
 * back out" and "I can see where out is" are now always true.
 */
export default function Dock({ autoHide = false }: { autoHide?: boolean }) {
  const pathname = usePathname();
  const [peek, setPeek] = useState(false);
  const { signOut, overlay } = useSignOut();

  // macOS marks running apps with a dot under the icon. Here "running" is
  // "this is the page you are on" — the same meaning the rail gave its white
  // active pill, in the idiom the dock already has.
  const openApps = useMemo(() => {
    const match = APPS.find((a) =>
      a.href === '/' ? pathname === '/' : Boolean(a.href) && pathname.startsWith(a.href!),
    );
    return match ? [match.id] : [];
  }, [pathname]);

  return (
    <>
      {/* The sign-out cover. Portalled to <body> by useSignOut, because the
          dock's own backdrop-filter would otherwise make a fixed overlay lay
          out inside the dock instead of over the screen. */}
      {overlay}
      {/* The reveal strip. Only when tucked away — a full-width invisible band
          at the very bottom of the viewport that the pointer runs into. Sits
          BELOW the dock in z-order so it never eats the dock's own hover. */}
      {autoHide && !peek && (
        <div
          className="fixed bottom-0 left-0 right-0 h-3 z-40"
          onMouseEnter={() => setPeek(true)}
          aria-hidden="true"
        />
      )}

      {/* Bottom-centre, floating clear of the window edge. Fixed rather than
          in-flow: the rail was a flex sibling that took horizontal space from
          every page, and a dock that pushed content up by its full height
          would waste the same space vertically. AppFrame pads the content
          instead, so short pages never sit underneath it. */}
      <div
        className={cn(
          'fixed bottom-4 left-1/2 z-50 flex justify-center max-w-[calc(100vw-1rem)]',
          'transition-transform duration-300 ease-out',
          // -50% keeps it centred; the Y term is what tucks it away. Both live
          // in one transform because a second one would overwrite the first.
          autoHide && !peek
            ? 'translate-x-[-50%] translate-y-[calc(100%+1rem)]'
            : 'translate-x-[-50%] translate-y-0',
        )}
        onMouseLeave={() => autoHide && setPeek(false)}
      >
        <MacOSDock
          apps={APPS}
          openApps={openApps}
          onAppClick={(id) => { if (id === 'logout') signOut(); }}
          surfaceClassName="lg-glass-dark"
          aria-label="Dock"
        />
      </div>
    </>
  );
}
