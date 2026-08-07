'use client';

/**
 * Dock icons — one squircle "app icon" per destination.
 *
 * The dock replaced the tool rail, and the rail's flat lucide glyphs read as
 * unfinished once they were sitting in a Dock: a Dock is a shelf of *apps*, and
 * apps have icons, not outlines. These are those icons.
 *
 * Colour is assigned by meaning, not decoration (Brand Guidelines v1.0). Every
 * gradient is mixed from two colours already in the Numera palette, or from the
 * ambient backdrop in globals.css, so the set reads as one family rather than a
 * pile of stock icons. The glyphs are the same lucide shapes the rail used, so
 * nobody has to relearn what anything is.
 */

import type { ReactElement, ReactNode } from 'react';

/**
 * A squircle, not a rounded rect. Straight edges through the middle of each
 * side, continuous curvature into the corners — the shape macOS and iOS use.
 * A plain `rx` rounded rect next to real app icons looks subtly wrong.
 */
const SQUIRCLE =
  'M22 .5H42C56 .5 63.5 8 63.5 22V42C63.5 56 56 63.5 42 63.5H22C8 63.5 .5 56 .5 42V22C.5 8 8 .5 22 .5Z';

function Tile({
  id,
  from,
  to,
  children,
}: {
  id: string;
  from: string;
  to: string;
  children: ReactNode;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width="100%"
      height="100%"
      aria-hidden="true"
      focusable="false"
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
        {/* Specular gloss across the top half — what makes it read as a
            physical tile rather than a coloured square. */}
        <linearGradient id={`${id}-gloss`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.30" />
          <stop offset="0.48" stopColor="#fff" stopOpacity="0.06" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>

      <path d={SQUIRCLE} fill={`url(#${id}-fill)`} />
      <path d={SQUIRCLE} fill={`url(#${id}-gloss)`} />
      {/* Bright rim, brightest at the top — light coming from above. */}
      <path
        d={SQUIRCLE}
        fill="none"
        stroke="rgba(255,255,255,0.38)"
        strokeWidth="1"
      />

      <g
        transform="translate(14 14) scale(1.5)"
        fill="none"
        stroke="#fff"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {children}
      </g>
    </svg>
  );
}

/* ── Lesson — the live learning moment ─────────────────────────── */
export const LessonIcon: ReactElement = (
  <Tile id="nd-lesson" from="#4169E1" to="#00B4D8">
    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    <path d="m15 5 4 4" />
  </Tile>
);

/* ── Workbook — secondary structure ────────────────────────────── */
export const WorkbookIcon: ReactElement = (
  <Tile id="nd-workbook" from="#5C7FA0" to="#1B2A4A">
    <path d="M12 7v14" />
    <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
  </Tile>
);

/* ── Group Challenge — social. Purple is borrowed from .lg-ambient so
      it stays inside the existing visual world, and keeps Challenge from
      colliding with the amber/orange the app already uses for alerts. ── */
export const ChallengeIcon: ReactElement = (
  <Tile id="nd-challenge" from="#8E6BD8" to="#4169E1">
    <polyline points="14.5 17.5 3 6 3 3 6 3 17.5 14.5" />
    <line x1="13" y1="19" x2="19" y2="13" />
    <line x1="16" y1="16" x2="20" y2="20" />
    <polyline points="14.5 6.5 18 3 21 3 21 6 17.5 9.5" />
    <line x1="5" y1="14" x2="9" y2="18" />
    <line x1="7" y1="17" x2="4" y2="20" />
    <line x1="3" y1="19" x2="5" y2="21" />
  </Tile>
);

/* ── Key Notes — "key formula / aha moment" is literally what
      highlight-amber is reserved for in the brand palette. ───────── */
export const KeyNotesIcon: ReactElement = (
  <Tile id="nd-keynotes" from="#FFC661" to="#FF9F1C">
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </Tile>
);

/* ── People — calm connection ──────────────────────────────────── */
export const PeopleIcon: ReactElement = (
  <Tile id="nd-people" from="#00B4D8" to="#008B8B">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </Tile>
);

/* ── Files — storage ───────────────────────────────────────────── */
export const FilesIcon: ReactElement = (
  <Tile id="nd-files" from="#4A6984" to="#008B8B">
    <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
  </Tile>
);

/* ── Flagged — the same orange History already uses for
      "WORTH ANOTHER LOOK". ───────────────────────────────────────── */
export const FlaggedIcon: ReactElement = (
  <Tile id="nd-flagged" from="#FFA53D" to="#F77F00">
    <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
    <line x1="4" y1="22" x2="4" y2="15" />
  </Tile>
);

/* ── Notifications — signal ────────────────────────────────────── */
export const NotificationsIcon: ReactElement = (
  <Tile id="nd-notifications" from="#3FD0EE" to="#4169E1">
    <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
    <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </Tile>
);

/* ── History — archival, the deepest blue in the set ───────────── */
export const HistoryIcon: ReactElement = (
  <Tile id="nd-history" from="#4A6984" to="#141F38">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </Tile>
);

/* ── Help & support — AI guidance ──────────────────────────────── */
export const HelpIcon: ReactElement = (
  <Tile id="nd-help" from="#008B8B" to="#00B4D8">
    <path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3" />
  </Tile>
);

/* ── Profile — the student themselves, so it takes the brand's own
      identity colour rather than a section colour. ── */
export const ProfileIcon: ReactElement = (
  <Tile id="nd-profile" from="#2F4470" to="#1B2A4A">
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21v-1a8 8 0 0 1 16 0v1" />
  </Tile>
);

/* ── Log out — the way out, asked for in the dock itself (Manjusha, 7 Aug).
      It also lives in Profile, which is where this used to be the ONLY way
      to reach it; the reasoning then was that a session-ending action should
      be somewhere you go on purpose rather than one tap away in a row of
      destinations. That concern is real and it has not gone away, so this
      tile is deliberately the quietest in the set: muted grey rather than a
      section colour, and last in the row, so it reads as "leave" and not as
      another place to visit. It is also absent from the lesson, where the
      dock is tucked away — which is exactly where a mis-tap would cost the
      most work. ── */
export const LogOutIcon: ReactElement = (
  <Tile id="nd-logout" from="#7C8794" to="#4A5563">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </Tile>
);
