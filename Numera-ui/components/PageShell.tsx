/**
 * Shared chrome for every non-lesson route, so all pages read as one app:
 * a bordered header (title + meta + optional action) above a scrollable body.
 * Small grayscale primitives (Chip, ProgressBar, IconBadge) live here too to
 * keep the page set visually consistent.
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/**
 * The measure every page on this shell shares.
 *
 * Wide enough that a worksheet or a topic list fills a laptop screen instead of
 * hugging the left edge, and capped so lines of prose stay readable on a large
 * monitor. Centred, because content stranded in the top-left corner of an
 * otherwise empty page was the thing that made these screens look unfinished.
 */
const MEASURE = 'mx-auto w-full max-w-[1080px]';

/**
 * The wider measure, for pages that are a grid of cards rather than prose.
 * Capping those at the reading measure stranded them in a narrow column on a
 * large screen and pushed everything below the fold for no reason. Opt-in, so
 * the pages that are genuinely prose keep their readable line length.
 */
const MEASURE_WIDE = 'mx-auto w-full max-w-[1500px]';

export default function PageShell({
  title,
  subtitle,
  action,
  wide = false,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  /** Use the wide measure and tighter gutters. For card grids, not prose. */
  wide?: boolean;
  children: ReactNode;
}) {
  const measure = wide ? MEASURE_WIDE : MEASURE;
  const gutter = wide ? 'px-6' : 'px-10';
  /*
   * The surface is opaque, not glass.
   *
   * This used `.lg-glass`, which is `rgba(255,255,255,0.6)` over the app's
   * ambient shader — so the vivid gradient read straight through every library
   * page. Body text sat on a moving blue wash, contrast failed, and nothing
   * registered as a surface sitting ON something. Glass is right for chrome
   * floating over a lesson; it is wrong for a page you read.
   *
   * Changed here rather than in `.lg-glass` itself: that class is shared with
   * the app chrome, where the effect is doing its job.
   */
  return (
    <main
      className="flex-1 min-w-0 flex flex-col rounded-2xl m-2 overflow-hidden bg-white border border-white/60"
      style={{ boxShadow: '0 10px 34px rgba(11,16,32,0.18)' }}
      aria-label={title}
    >
      {/* Header and body share one centred measure. Previously the header ran
          the full width while pages set their own (usually narrower) max-width,
          so the title floated far left of the content it belonged to and the
          whole page hung off the top-left corner of a wide screen. */}
      <header className={cn('border-b border-white/40 py-8 flex-shrink-0', gutter)}>
        <div className={cn(measure, 'flex items-end justify-between gap-4')}>
          <div>
            <h1 className="text-[30px] font-semibold text-ink leading-[1.15] tracking-[-0.02em]">
              {title}
            </h1>
            {subtitle && <p className="text-[14px] text-slate-blue mt-1.5">{subtitle}</p>}
          </div>
          {action}
        </div>
      </header>
      {/* pb clears the dock. It floats bottom-centre over this surface, so
          without it the last row of any page is unreachable — you can scroll
          to the bottom and the dock is still sitting on top of it. Padding
          belongs on the scroll container, not on AppFrame: this is the element
          that actually scrolls. */}
      <div className={cn('flex-1 overflow-y-auto pt-9 pb-32', gutter)}>
        <div className={measure}>{children}</div>
      </div>
    </main>
  );
}

/** Small uppercase status label. */
export function Chip({
  children,
  tone = 'muted',
}: {
  children: ReactNode;
  tone?: 'muted' | 'solid' | 'outline';
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] tracking-[0.4px] uppercase',
        tone === 'solid' && 'bg-focus-navy text-white',
        tone === 'outline' && 'border border-muted-gray text-slate-blue',
        tone === 'muted' && 'bg-reading-surface text-slate-blue'
      )}
    >
      {children}
    </span>
  );
}

/** Thin grayscale progress bar (0–100). */
export function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1.5 w-full rounded-full bg-muted-gray overflow-hidden">
      <div className="h-full rounded-full bg-learning-blue" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Shimmering grey placeholder block for loading states. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted-gray', className)} />;
}

/** Centered empty/placeholder panel for "nothing here yet" states. */
export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center rounded-lg border border-dashed border-muted-gray bg-reading-surface px-8 py-14">
      {icon && (
        <span className="w-11 h-11 rounded-xl border border-muted-gray bg-white text-slate-blue flex items-center justify-center mb-3">
          {icon}
        </span>
      )}
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      {body && <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Square icon tile used in list rows. */
export function IconBadge({ children }: { children: ReactNode }) {
  return (
    <span className="flex-shrink-0 w-10 h-10 rounded-lg border border-muted-gray bg-reading-surface text-ink flex items-center justify-center">
      {children}
    </span>
  );
}

/** Circular initials avatar. */
export function Avatar({ name }: { name: string }) {
  const initials = name
    .split(' ')
    .map((n) => n[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <span className="flex-shrink-0 w-10 h-10 rounded-full border border-muted-gray bg-white text-ink flex items-center justify-center text-[12px] font-semibold tracking-[0.5px]">
      {initials}
    </span>
  );
}
