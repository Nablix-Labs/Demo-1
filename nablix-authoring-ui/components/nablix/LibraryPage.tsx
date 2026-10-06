import Link from 'next/link';
import { Topbar } from './Topbar';
import { HealthBadge } from './HealthBadge';
import type { ContentHealth } from '@/lib/api/v3-contracts';

/** Full-page shell for the cross-topic library screens: topbar + editorial
 *  masthead + scrolling body, matching the Dashboard's rhythm. */
export function LibraryPage({
  crumb,
  eyebrow,
  title,
  description,
  action,
  children,
}: {
  crumb: string;
  eyebrow: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      <Topbar title="Content Authoring Portal" crumb={crumb} />
      <main className="lg-scroll flex-1 overflow-y-auto px-6 pb-10">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-2xs font-bold uppercase tracking-[0.2em] text-slate-blue">{eyebrow}</div>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-focus-navy">{title}</h1>
            {description && <p className="mt-1 max-w-2xl text-sm text-slate-blue">{description}</p>}
          </div>
          {action}
        </div>
        {children}
      </main>
    </>
  );
}

/** Topic tag chip used across library tables. With `href` it links to that
 *  topic's workspace page; `title` shows the topic name on hover. */
export function TopicTag({ code, href, title }: { code: string; href?: string; title?: string }) {
  const chip = (
    <span
      title={title}
      className="rounded bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-bold text-learning-blue ring-1 ring-inset ring-muted-gray/70"
    >
      {code}
    </span>
  );
  return href ? <Link href={href} className="hover:opacity-80">{chip}</Link> : chip;
}

/** The load failed outright, or some topics' pages did — said plainly, never hidden. */
export function LibraryNotice({ error, failed }: { error?: string | null; failed?: string[] }) {
  if (error) {
    return <p className="mb-3 text-sm font-semibold text-danger">Could not load this library: {error}</p>;
  }
  if (!failed?.length) return null;
  return (
    <p className="mb-3 text-sm font-semibold text-action-orange">
      Could not load {failed.length === 1 ? 'topic' : 'topics'} {failed.join(', ')} — showing the rest.
    </p>
  );
}

const HEALTH_STATES = ['COMPLETE', 'WARNING', 'MISSING'];

/** HealthBadge for a library row; renders nothing when the row sent no
 *  recognisable health, rather than crashing the whole list. */
export function RowHealth({ health, showLabel }: { health?: ContentHealth | null; showLabel?: boolean }) {
  if (!health || !HEALTH_STATES.includes(health.state)) return null;
  return <HealthBadge health={health} showLabel={showLabel} />;
}
