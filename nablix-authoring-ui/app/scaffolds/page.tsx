'use client';

import { Layers, ArrowRight } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { loadScaffolds } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';

export default function GlobalScaffolds() {
  const { data, error } = useLibrary(loadScaffolds);
  const rows = data?.rows ?? null;

  return (
    <LibraryPage
      crumb="Scaffolds"
      eyebrow="Library · Scaffolds"
      title="Scaffold Library"
      description="Step-by-step recovery routes across topics, with their stages and completion rules."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <div className="grid gap-3 lg:grid-cols-2">
        {rows === null
          ? !error && Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-48 animate-pulse rounded-card bg-white/50" />)
          : rows.length === 0
            ? <p className="text-sm text-slate-blue">No scaffolds in live content.</p>
            : rows.map((s) => {
              const steps = s.children?.steps ?? [];
              const links = s.children?.question_links ?? [];
              return (
                <section key={`${s.topic_id}-${s.scaffold_id}`} className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
                  <div className="flex items-center justify-between gap-2 border-b border-muted-gray/70 px-5 py-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <Layers className="h-4 w-4 shrink-0 text-learning-blue" />
                      <h3 className="truncate font-display text-sm font-bold text-focus-navy">{s.details?.scaffold_name ?? s.label}</h3>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <TopicTag code={s.topic_code} title={s.topic_title} href={`/topics/${s.topic_id}/scaffolds`} />
                      <RowHealth health={s.content_health} />
                      {s.details && <StatusPill status={s.details.active ? 'ACTIVE' : 'INACTIVE'} />}
                    </div>
                  </div>
                  <div className="px-5 py-3">
                    {s.details?.trigger_rule && <p className="text-xs text-slate-blue"><span className="font-semibold">Trigger · </span>{s.details.trigger_rule}</p>}
                    {s.details?.completion_rule && <p className="mt-0.5 text-xs text-slate-blue"><span className="font-semibold">Complete · </span>{s.details.completion_rule}</p>}
                    <p className="mt-1 text-2xs font-semibold text-slate-blue/80">
                      {steps.length} stage{steps.length === 1 ? '' : 's'} · {links.length} linked question{links.length === 1 ? '' : 's'}
                    </p>
                    <ol className="mt-2 space-y-1.5">
                      {steps.map((st) => (
                        <li key={st.scaffold_step_id ?? st.stage_no} className="flex items-center gap-2 rounded-lg bg-reading-surface px-3 py-2 text-xs">
                          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">{st.stage_no}</span>
                          <span className="min-w-0 flex-1 truncate text-ink">{st.prompt}</span>
                          <ArrowRight className="h-3 w-3 text-slate-blue/50" />
                          <span className="font-mono text-2xs text-slate-blue">{st.next_on_correct}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                </section>
              );
            })}
      </div>
    </LibraryPage>
  );
}
