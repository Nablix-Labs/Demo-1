'use client';

/**
 * ScreenMarks — the drawn marks for CenteredScreen.
 *
 * These replace the scaled-up lucide glyphs. A UI icon is built to read at
 * 20px; at 200px it looks like a wireframe, and a wireframe is the wrong voice
 * for an eleven-year-old about to be tested on algebra. These are characters
 * instead — Numi, the tutor, doing the thing the screen is about.
 *
 * House rules so the set reads as one family:
 *   - filled shapes, not outlines: fills read as friendly, strokes read clinical
 *   - one navy outline weight (3.5) around the character, nothing thinner
 *   - the brand blues for the body, cyan reserved for the one spark of accent
 *   - eyes are simple dots with a single highlight — no eyebrows, no mouths
 *     beyond one curve. Expression comes from the pose.
 */

import type { CSSProperties } from 'react';

export interface MarkProps {
  size?: number;
  className?: string;
  style?: CSSProperties;
  /** Paint server id, supplied by ScreenIcon. Unused by character marks, which
   *  carry their own fills. */
  gradientId?: string;
}

const NAVY = '#1B2A4A';
const FACE = '#F6FAFF';

/** The gradients every mark paints Numi with, defined once per svg. */
function NumiDefs() {
  return (
    <defs>
      <linearGradient id="numi-body" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor="#6C97F2" />
        <stop offset="100%" stopColor="#3F63D6" />
      </linearGradient>
      <linearGradient id="numi-glass" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.85" />
        <stop offset="100%" stopColor="#00B4D8" stopOpacity="0.28" />
      </linearGradient>
    </defs>
  );
}

/**
 * Numi himself: antenna, feet, body, face. No arms — each mark adds its own,
 * because what he is DOING is the whole point of the mark.
 *
 * Drawn on the 120-unit grid and positioned with a transform, so two of him can
 * stand side by side (see GroupMark) without any of the geometry being redone.
 */
function NumiFigure({
  transform,
  mouth = 'smile',
}: {
  transform?: string;
  /** smile for the ordinary path, flat when the screen is a stop. */
  mouth?: 'smile' | 'flat';
}) {
  return (
    <g transform={transform}>
      <path d="M42 34v-9" stroke={NAVY} strokeWidth={3.5} strokeLinecap="round" />
      <circle cx="42" cy="20" r="5" fill="#00B4D8" stroke={NAVY} strokeWidth={3.5} />

      <ellipse cx="31" cy="98" rx="9.5" ry="6" fill={NAVY} />
      <ellipse cx="56" cy="98" rx="9.5" ry="6" fill={NAVY} />

      <rect
        x="12" y="32" width="62" height="62" rx="24"
        fill="url(#numi-body)" stroke={NAVY} strokeWidth={3.5}
      />

      <rect x="21" y="44" width="44" height="31" rx="14" fill={FACE} />
      <circle cx="36" cy="58" r="4.6" fill={NAVY} />
      <circle cx="54" cy="58" r="4.6" fill={NAVY} />
      <circle cx="37.6" cy="56.2" r="1.6" fill="#FFFFFF" />
      <circle cx="55.6" cy="56.2" r="1.6" fill="#FFFFFF" />

      <ellipse cx="26" cy="67" rx="4" ry="2.4" fill="#00B4D8" opacity="0.35" />
      <ellipse cx="63" cy="67" rx="4" ry="2.4" fill="#00B4D8" opacity="0.35" />

      <path
        d={mouth === 'smile' ? 'M39 66.5q6 5.5 12 0' : 'M40 68h10'}
        stroke={NAVY} strokeWidth={3.2} strokeLinecap="round"
      />
    </g>
  );
}

/**
 * Placement — the topic-entry diagnostic ("Quick check before we start").
 *
 * Numi with a magnifying glass: the screen is about having a look at what you
 * already know, so the character is looking, not testing. The glass is held up
 * and away from the face so it stays legible as an object rather than becoming
 * a monocle.
 */
export function PlacementMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      fill="none"
      aria-hidden
      className={className}
      style={style}
    >
      <defs>
        <linearGradient id="numi-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6C97F2" />
          <stop offset="100%" stopColor="#3F63D6" />
        </linearGradient>
        <linearGradient id="numi-glass" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.85" />
          <stop offset="100%" stopColor="#00B4D8" stopOpacity="0.28" />
        </linearGradient>
      </defs>

      {/* antenna — the one cyan accent */}
      <path d="M42 34v-9" stroke={NAVY} strokeWidth={3.5} strokeLinecap="round" />
      <circle cx="42" cy="20" r="5" fill="#00B4D8" stroke={NAVY} strokeWidth={3.5} />

      {/* feet, drawn first so the body sits over their tops */}
      <ellipse cx="31" cy="98" rx="9.5" ry="6" fill={NAVY} />
      <ellipse cx="56" cy="98" rx="9.5" ry="6" fill={NAVY} />

      {/* body */}
      <rect
        x="12"
        y="32"
        width="62"
        height="62"
        rx="24"
        fill="url(#numi-body)"
        stroke={NAVY}
        strokeWidth={3.5}
      />

      {/* left arm, resting. Drawn after the body so it reads as attached to it
          rather than passing behind it. */}
      <path
        d="M15 70c-4 3-6 6-7 10"
        stroke={NAVY}
        strokeWidth={4.5}
        strokeLinecap="round"
      />
      <circle cx="8" cy="83" r="6" fill={FACE} stroke={NAVY} strokeWidth={3.5} />

      {/* face plate */}
      <rect x="21" y="44" width="44" height="31" rx="14" fill={FACE} />

      {/* eyes, both looking towards the glass */}
      <circle cx="36" cy="58" r="4.6" fill={NAVY} />
      <circle cx="54" cy="58" r="4.6" fill={NAVY} />
      <circle cx="37.6" cy="56.2" r="1.6" fill="#FFFFFF" />
      <circle cx="55.6" cy="56.2" r="1.6" fill="#FFFFFF" />

      {/* blush */}
      <ellipse cx="26" cy="67" rx="4" ry="2.4" fill="#00B4D8" opacity="0.35" />
      <ellipse cx="63" cy="67" rx="4" ry="2.4" fill="#00B4D8" opacity="0.35" />

      {/* smile */}
      <path
        d="M39 66.5q6 5.5 12 0"
        stroke={NAVY}
        strokeWidth={3.2}
        strokeLinecap="round"
      />

      {/* Right arm, raised to hold the glass. The order below is the whole
          trick: arm, then handle, then ring, then hand last — so the hand
          closes over the handle and the grip reads as a grip. */}
      <path
        d="M70 68c5 1 9 0 12-3"
        stroke={NAVY}
        strokeWidth={4.5}
        strokeLinecap="round"
      />
      <path
        d="M91 54 83 63"
        stroke={NAVY}
        strokeWidth={7}
        strokeLinecap="round"
      />
      <circle cx="99" cy="42" r="16" fill="url(#numi-glass)" stroke={NAVY} strokeWidth={5} />
      {/* glint */}
      <path
        d="M91 36a10 10 0 0 1 6-5"
        stroke="#FFFFFF"
        strokeWidth={3}
        strokeLinecap="round"
        opacity="0.9"
      />
      <circle cx="84" cy="63" r="6.5" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
    </svg>
  );
}

/**
 * Celebration — course complete, and "you're all set" after the placement check.
 *
 * Arms up. The alternative was a tick, and a 300px tick is a form the student
 * has already seen a hundred times on this screen as feedback for a single
 * answer; using it again for finishing a course flattens the difference between
 * "that was right" and "you're done".
 */
export function CelebrationMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden className={className} style={style}>
      <NumiDefs />

      {/* sparks, thrown where the hands are going */}
      <g stroke="#00B4D8" strokeWidth={3.5} strokeLinecap="round">
        <path d="M8 36 4 30M14 26l-2-7M2 46l-7-1" />
        <path d="M92 30l6-6M84 20l2-7M100 40l7-2" />
      </g>

      <NumiFigure />

      {/* Both arms raised. Held well clear of the head — drawn closer in, the
          hands sat level with the face and read as ears. */}
      <path d="M15 62C9 54 5 44 3 34" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="2" cy="29" r="6.5" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
      <path d="M71 62c6-8 10-18 12-28" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="84" cy="29" r="6.5" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
    </svg>
  );
}

/**
 * Group — the group challenge.
 *
 * Two of him, one behind and smaller, so it reads as "some of you" rather than
 * a crowd. The lucide Users glyph was doing this job and at 300px its second
 * figure rendered as a detached fragment.
 *
 * A raised hand between them was tried and cut: at this size it overlapped the
 * second face and read as a collision rather than a gesture. Two of him is
 * already the whole idea.
 */
export function GroupMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden className={className} style={style}>
      <NumiDefs />
      {/* the one behind: smaller, pushed back, drawn first */}
      <g opacity="0.55">
        <NumiFigure transform="translate(52 20) scale(0.62)" />
      </g>
      <NumiFigure transform="translate(-4 6) scale(0.9)" />
    </svg>
  );
}

/**
 * Locked — a phase whose prerequisite is not finished.
 *
 * Numi holds the padlock rather than standing behind bars: the screen is "not
 * yet, here's what to do first", and a character guarding a lock is friendlier
 * than a character imprisoned by one. Mouth flat, not sad — this is a wait, not
 * a failure.
 */
export function LockedMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden className={className} style={style}>
      <NumiDefs />
      <NumiFigure mouth="flat" />
      {/* arm out to the padlock */}
      <path d="M70 68c5 1 9 0 12-3" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      {/* padlock: shackle, then body, then the hand closing over it */}
      <path d="M88 46v-6a9 9 0 0 1 18 0v6" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <rect x="84" y="46" width="26" height="22" rx="6" fill="url(#numi-body)" stroke={NAVY} strokeWidth={3.5} />
      <circle cx="97" cy="56" r="3" fill={NAVY} />
      <circle cx="84" cy="63" r="6.5" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
    </svg>
  );
}

/**
 * Problem — a failure the student cannot fix themselves (load error, retry).
 *
 * Numi shrugging with a single mark above him. No red, no warning triangle: the
 * student has done nothing wrong, and dressing a backend timeout as an alert
 * makes them think they have.
 */
export function ProblemMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden className={className} style={style}>
      <NumiDefs />
      <g stroke={NAVY} strokeWidth={4.5} strokeLinecap="round">
        <path d="M86 30v14" />
      </g>
      <circle cx="86" cy="52" r="2.8" fill={NAVY} />
      <NumiFigure mouth="flat" />
      {/* both arms out in a shrug */}
      <path d="M14 64c-5 0-8 2-10 5" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="1" cy="72" r="6" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
      <path d="M72 64c5 0 8 2 10 5" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="85" cy="72" r="6" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
    </svg>
  );
}

/**
 * Encourage — a screen with nothing on it yet.
 *
 * Numi waving, no sparks. The completion screen is reachable with zero topics
 * mastered, and showing the celebration there congratulated a student for
 * finishing nothing while a list of dashes sat underneath it (2026-07-29).
 * An empty state should invite, not applaud.
 */
export function EncourageMark({ size = 200, className, style }: MarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" aria-hidden className={className} style={style}>
      <NumiDefs />
      <NumiFigure />
      {/* resting arm */}
      <path d="M15 70c-4 3-6 6-7 10" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="8" cy="83" r="6" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
      {/* waving arm */}
      <path d="M71 62c6-5 9-11 10-17" stroke={NAVY} strokeWidth={4.5} strokeLinecap="round" />
      <circle cx="82" cy="41" r="6.5" fill={FACE} stroke={NAVY} strokeWidth={3.5} />
    </svg>
  );
}
