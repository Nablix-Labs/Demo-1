/**
 * Shared chrome for every non-lesson route, so all pages read as one app:
 * a bordered header (title + meta + optional action) above a scrollable body.
 * Small grayscale primitives (Chip, ProgressBar, IconBadge) live here too to
 * keep the page set visually consistent.
 */
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export default function PageShell({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="lg-glass flex-1 min-w-0 flex flex-col rounded-2xl m-2 overflow-hidden" aria-label={title}>
      <header className="flex items-end justify-between gap-4 px-8 py-6 border-b border-white/40 flex-shrink-0">
        <div>
          <h1 className="text-[22px] font-semibold text-ink leading-tight">{title}</h1>
          {subtitle && <p className="text-[12px] text-slate-blue mt-1">{subtitle}</p>}
        </div>
        {action}
      </header>
      <div className="flex-1 overflow-y-auto px-8 py-7">{children}</div>
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
