'use client';

/**
 * Dock icons — one squircle "app icon" per destination.
 *
 * The dock replaced the tool rail, and the rail's flat lucide glyphs read as
 * unfinished once they were sitting in a Dock: a Dock is a shelf of *apps*, and
 * apps have icons, not outlines. These are those icons.
 *
 * Colour is assigned by meaning, not decoration (Brand Guidelines v1.0). The
 * three tiles the palette actually names keep its colours — Lesson is
 * learning-blue into ai-cyan, Key Notes is highlight-amber, Help is dark-cyan.
 * The rest are extended from it, because the palette is a brand palette and not
 * a twelve-way categorical scale: eight of these twelve used to sit in the
 * blue/cyan/navy band and were unreadable as separate things at 44px.
 *
 * Two rules hold the set together, and both are why it stopped working before:
 *
 *  1. NEIGHBOURS DIFFER IN HUE. The dock is a fixed row, so what matters is not
 *     that twelve colours exist but that no tile touches another from its own
 *     family. Read left to right the set now runs blue, green, violet, amber,
 *     rose, bronze, crimson, lime, indigo, teal, steel, grey.
 *
 *  2. NOTHING ENDS DARKER THAN THE DOCK. Workbook, History and Profile used to
 *     finish on #1B2A4A and #141F38 — darker than the .lg-glass-dark surface
 *     they sit on, so they read as holes punched in the shelf rather than as
 *     app icons. Every gradient now ends well above that floor.
 *
 * What is NOT bold is as deliberate as what is: Profile and Log out stay quiet
 * because neither is a place you go looking for mid-lesson, and the two loudest
 * tiles are Flagged and Notifications, whose whole job is to be noticed.
 *
 * The glyphs are the same lucide shapes the rail used, so nobody has to
 * relearn what anything is.
 *
 * Ten tiles are now 3D illustrations (ArtTile, 6 Oct). Key Notes and People
 * keep their glyph tiles until their art is made.
 */

import type { ReactElement, ReactNode } from 'react';
import { art } from '@/lib/art';

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

/**
 * A 3D illustrated icon (Midjourney, public/art/dock) on a white squircle.
 *
 * The art comes on white, so the tile is white and the picture needs no
 * cut-out — a cut-out left a grey shadow halo on the dark dock. Clipped to the
 * same squircle as Tile, so both kinds sit in one row.
 */
function ArtTile({ id, src }: { id: string; src: string }) {
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
        <clipPath id={`${id}-clip`}>
          <path d={SQUIRCLE} />
        </clipPath>
      </defs>
      <path d={SQUIRCLE} fill="#FFFFFF" />
      <image
        href={src}
        x="3"
        y="3"
        width="58"
        height="58"
        preserveAspectRatio="xMidYMid meet"
        clipPath={`url(#${id}-clip)`}
      />
      <path d={SQUIRCLE} fill="none" stroke="rgba(255,255,255,0.6)" strokeWidth="1" />
    </svg>
  );
}

/* ── Lesson — the live learning moment ─────────────────────────── */
export const LessonIcon: ReactElement = <ArtTile id="nd-lesson" src={art('dock/lesson')} />;

/* ── Workbook — practice you accumulate, so it grows: green, and the
      first tile that used to end in near-black navy. ───────────────── */
export const WorkbookIcon: ReactElement = <ArtTile id="nd-workbook" src={art('dock/workbook')} />;

/* ── Group Challenge — social. Purple is borrowed from .lg-ambient so
      it stays inside the existing visual world, and keeps Challenge from
      colliding with the amber/orange the app already uses for alerts. ── */
export const ChallengeIcon: ReactElement = <ArtTile id="nd-challenge" src={art('dock/challenge')} />;

/* ── Key Notes — "key formula / aha moment" is literally what
      highlight-amber is reserved for in the brand palette. ───────── */
export const KeyNotesIcon: ReactElement = (
  <Tile id="nd-keynotes" from="#FFD076" to="#FF9F1C">
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </Tile>
);

/* ── People — the only tile about other humans, so it is the only warm
      pink in the set. ─────────────────────────────────────────────── */
export const PeopleIcon: ReactElement = (
  <Tile id="nd-people" from="#FF9AAE" to="#E5476F">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </Tile>
);

/* ── Files — paper and folders: bronze, the material colour. ────── */
export const FilesIcon: ReactElement = <ArtTile id="nd-files" src={art('dock/files')} />;

/* ── Flagged — was orange, which collided with Key Notes two tiles
      away and read as another highlight. Crimson: this is the pile you
      got wrong, not the pile worth remembering. ─────────────────────── */
export const FlaggedIcon: ReactElement = <ArtTile id="nd-flagged" src={art('dock/flagged')} />;

/* ── Notifications — a signal has to cut through, and every other cool
      colour was taken by a destination. Lime is the loudest thing on the
      shelf and the only tile allowed to be. ─────────────────────────── */
export const NotificationsIcon: ReactElement = <ArtTile id="nd-notifications" src={art('dock/notifications')} />;

/* ── History — indigo. It was the deepest blue in the set, which on a
      dark shelf meant it was barely a tile at all. ──────────────────── */
export const HistoryIcon: ReactElement = <ArtTile id="nd-history" src={art('dock/history')} />;

/* ── Help & support — AI guidance ──────────────────────────────── */
export const HelpIcon: ReactElement = <ArtTile id="nd-help" src={art('dock/help')} />;

/* ── Profile — the student themselves, so it takes the brand's own
      identity colour rather than a section colour. ── */
export const ProfileIcon: ReactElement = <ArtTile id="nd-profile" src={art('dock/profile')} />;

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
export const LogOutIcon: ReactElement = <ArtTile id="nd-logout" src={art('dock/logout')} />;
