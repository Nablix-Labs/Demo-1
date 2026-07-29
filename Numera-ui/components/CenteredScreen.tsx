'use client';

/**
 * CenteredScreen — the full-page "one thing to read, one thing to do" screen.
 *
 * Used by every gate, intro, result and error state in the learning flow: the
 * diagnostic intro, the phase-locked gate, "You're all set", course complete,
 * the group-challenge start, /restricted. Eleven copies of the same markup were
 * living in eight files and had already drifted apart — three tile skins, four
 * icon sizes, three corner radii — so it is factored here instead.
 *
 * Two deliberate choices, both from Manav on 2026-07-29:
 *   - The icon has no container. It used to sit in a 48px navy rounded square,
 *     which read as a button and competed with the real one below it. Now it is
 *     drawn large and bare, so it registers as an illustration.
 *   - The background is the Waves shader rather than flat white.
 */

import type { LucideIcon } from 'lucide-react';
import type { MarkProps } from '@/components/ScreenMarks';
import type { ReactElement, ReactNode } from 'react';
import { ShaderBackground } from '@/components/ui/waves-shaders-homlu-ui';
import { cn } from '@/lib/cn';

export function CenteredScreen({
  children,
  label,
  width = 680,
  busy,
}: {
  children: ReactNode;
  /** Accessible name for the screen, e.g. "Orientation locked". */
  label?: string;
  /** Column width in px. 560 for short screens, 680 for the rest. */
  width?: 560 | 680;
  busy?: boolean;
}) {
  return (
    <main
      className="relative flex-1 min-w-0 flex items-center justify-center overflow-hidden bg-off-white p-8"
      aria-label={label}
      aria-busy={busy}
    >
      {/* Sits behind the content and takes no clicks. The canvas pauses itself
          when off-screen or on a hidden tab, and holds still under
          prefers-reduced-motion.

          The parent carries a light background of its own so that a canvas
          which fails to draw — a lost WebGL context, a GPU-blocked browser —
          leaves the screen light and readable rather than whatever the dead
          canvas last held. The text on these screens is near-black, so a dark
          background is not a cosmetic problem, it is an unreadable one. */}
      <ShaderBackground className="pointer-events-none absolute inset-0" />
      {/* The type scale lives here rather than in the eleven screens that use
          this shell — they each hard-coded 22px headings and 13px body, which
          read as fine print once the screen became a full-bleed background.
          Descendant selectors outrank the utility classes already on those
          elements, so the screens need no edit to pick this up. */}
      <div
        className={cn(
          'relative max-w-full text-center',
          '[&_h1]:text-[40px] [&_h1]:leading-[1.08] [&_h1]:tracking-[-0.025em]',
          '[&_p]:text-[17px] [&_p]:leading-relaxed',
          '[&_.uppercase]:text-[11px] [&_.uppercase]:tracking-[0.2em]',
          '[&_button]:text-[16px] [&_a]:text-[16px]',
        )}
        style={{ width: `${width}px` }}
      >
        {children}
      </div>
    </main>
  );
}

/**
 * The oversized mark at the top of a CenteredScreen.
 *
 * A lucide glyph scaled to 200px reads as a blown-up UI icon — a hairline
 * wireframe with no weight. Three things fix that, and all three are what make
 * this a mark rather than an icon:
 *
 *   - a soft halo behind it, so it sits ON the shader instead of floating over it
 *   - a gradient stroke, navy at the top falling to brand blue at the bottom,
 *     which follows the same direction the background gradient runs
 *   - a stroke weight set in real pixels for this size (absoluteStrokeWidth),
 *     not the 1.8 grid units that suit a 22px icon and would scale to a slab
 *
 * `tone` carries the screen's meaning, not decoration: navy is the ordinary
 * path forward, muted is a stop (locked, error, restricted).
 */
export function ScreenIcon({
  icon: Icon,
  mark: Mark,
  tone = 'navy',
  className,
}: {
  /** A lucide glyph. Screens still on this are waiting for a drawn mark. */
  icon?: LucideIcon;
  /** A drawn mark from ScreenMarks — preferred; see the note there. */
  mark?: (p: MarkProps) => ReactElement;
  tone?: 'navy' | 'muted';
  className?: string;
}) {
  const gradientId = tone === 'navy' ? 'numera-mark-navy' : 'numera-mark-muted';

  return (
    <div className={cn('relative mx-auto mb-8 h-[300px] w-[300px]', className)}>
      {/* Paint server for the stroke below. SVG gradients resolve by document
          id, so this can live in its own zero-size svg. */}
      <svg width="0" height="0" aria-hidden className="absolute">
        <defs>
          <linearGradient id="numera-mark-navy" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1B2A4A" />
            <stop offset="100%" stopColor="#4169E1" />
          </linearGradient>
          <linearGradient id="numera-mark-muted" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4A6984" />
            <stop offset="100%" stopColor="#8FA6BC" />
          </linearGradient>
        </defs>
      </svg>

      {/* Halo. Kept very low contrast: it should register as light behind the
          mark, never as a visible disc. */}
      <div
        aria-hidden
        className="absolute inset-0 rounded-full blur-2xl"
        style={{
          background:
            tone === 'navy'
              ? 'radial-gradient(circle, rgba(65,105,225,0.22) 0%, rgba(65,105,225,0) 70%)'
              : 'radial-gradient(circle, rgba(74,105,132,0.16) 0%, rgba(74,105,132,0) 70%)',
        }}
      />

      {Mark ? (
        <Mark size={300} gradientId={gradientId} className="relative block" />
      ) : Icon ? (
        <Icon
          size={300}
          strokeWidth={9}
          absoluteStrokeWidth
          aria-hidden
          className="relative block"
          style={{ stroke: `url(#${gradientId})` }}
        />
      ) : null}
    </div>
  );
}
