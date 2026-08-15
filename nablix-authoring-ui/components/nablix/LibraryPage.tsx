import { Topbar } from './Topbar';

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

/** Topic tag chip used across library tables. */
export function TopicTag({ code }: { code: string }) {
  return (
    <span className="rounded bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-bold text-learning-blue ring-1 ring-inset ring-muted-gray/70">
      {code}
    </span>
  );
}
