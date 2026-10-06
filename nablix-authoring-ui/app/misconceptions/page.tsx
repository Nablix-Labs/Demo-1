'use client';

import { useMemo } from 'react';
import { Brain, AlertOctagon } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { loadMisconceptions, type TopicStamp } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';
import { cn } from '@/lib/utils';

const REL: Record<string, string> = {
  DIRECT_FAILURE: 'bg-danger/10 text-danger',
  UNDERLYING_GAP: 'bg-highlight-amber/12 text-action-orange',
  AFFECTED_SKILL: 'bg-learning-blue/12 text-learning-blue',
};

const COUNT_LABELS: Record<string, string> = {
  linked_errors: 'errors',
  linked_micro_skills: 'skills',
  hints: 'hints',
  visual_cues: 'cues',
  parallel_examples: 'parallel examples',
};

interface ErrorRow extends TopicStamp {
  error_code: string;
  label: string;
  misconception_count: number;
}

export default function GlobalMisconc() {
  const { data, error } = useLibrary(loadMisconceptions);
  const rows = data?.rows ?? null;

  // There is no error-type endpoint: the error types listed are the ones the
  // misconceptions link to, once per topic.
  const errors = useMemo(() => {
    const byKey = new Map<string, ErrorRow>();
    for (const m of rows ?? []) {
      for (const e of m.children?.linked_errors ?? []) {
        const key = `${m.topic_id}|${e.error_code}`;
        const seen = byKey.get(key);
        if (seen) seen.misconception_count += 1;
        else byKey.set(key, { topic_id: m.topic_id, topic_code: m.topic_code, topic_title: m.topic_title, error_code: e.error_code, label: e.label, misconception_count: 1 });
      }
    }
    return [...byKey.values()];
  }, [rows]);

  const skeleton = !error && Array.from({ length: 3 }).map((_, i) => <li key={i} className="px-5 py-3"><div className="h-6 animate-pulse rounded bg-reading-surface" /></li>);

  return (
    <LibraryPage
      crumb="Misconceptions"
      eyebrow="Library · Errors & Misconceptions"
      title="Misconception Library"
      description="Every misconception across topics, with the error types and micro-skills it links to."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        {/* Error types linked from misconceptions */}
        <section className="h-fit overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
          <div className="flex items-center gap-2 border-b border-muted-gray/70 px-5 py-3">
            <AlertOctagon className="h-4 w-4 text-learning-blue" />
            <h2 className="font-display text-base font-bold text-focus-navy">Linked Error Types</h2>
          </div>
          <ul className="divide-y divide-muted-gray/50">
            {rows === null ? skeleton : errors.length === 0 ? (
              <li className="px-5 py-4 text-sm text-slate-blue">No linked error types.</li>
            ) : errors.map((e) => (
              <li key={`${e.topic_id}-${e.error_code}`} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <TopicTag code={e.topic_code} title={e.topic_title} href={`/topics/${e.topic_id}/misconceptions`} />
                  <span className="font-mono text-2xs font-bold text-focus-navy">{e.error_code}</span>
                </div>
                <div className="mt-0.5 text-sm font-semibold text-ink">{e.label}</div>
                <p className="text-xs text-slate-blue">Linked from {e.misconception_count} misconception{e.misconception_count === 1 ? '' : 's'}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Misconceptions */}
        <section className="h-fit overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
          <div className="flex items-center gap-2 border-b border-muted-gray/70 px-5 py-3">
            <Brain className="h-4 w-4 text-learning-blue" />
            <h2 className="font-display text-base font-bold text-focus-navy">Misconceptions</h2>
            {rows && <span className="ml-auto text-2xs font-semibold text-slate-blue">{rows.length}</span>}
          </div>
          <ul className="divide-y divide-muted-gray/50">
            {rows === null ? skeleton : rows.length === 0 ? (
              <li className="px-5 py-4 text-sm text-slate-blue">No misconceptions in live content.</li>
            ) : rows.map((m) => (
              <li key={`${m.topic_id}-${m.misconception_id}`} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <TopicTag code={m.topic_code} title={m.topic_title} href={`/topics/${m.topic_id}/misconceptions`} />
                  <h3 className="min-w-0 flex-1 text-sm font-bold text-focus-navy">{m.label}</h3>
                  <RowHealth health={m.content_health} />
                </div>
                <div className="mt-0.5 font-mono text-2xs text-slate-blue/70">{m.misconception_id}</div>
                {m.child_counts && (
                  <p className="mt-1 text-xs text-slate-blue">
                    {Object.entries(m.child_counts).map(([k, n]) => `${n} ${COUNT_LABELS[k] ?? k.replace(/_/g, ' ')}`).join(' · ')}
                  </p>
                )}
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {(m.children?.linked_errors ?? []).map((e) => <span key={e.error_code} title={e.label} className="rounded bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-semibold text-focus-navy ring-1 ring-inset ring-muted-gray/70">{e.error_code}</span>)}
                  {(m.children?.linked_micro_skills ?? []).map((s) => <span key={s.micro_skill_id} title={s.label} className={cn('rounded px-1.5 py-0.5 text-2xs font-semibold', REL[s.relationship_type] ?? 'bg-reading-surface text-slate-blue')}>{s.micro_skill_id.split('.').pop()} · {s.relationship_type.replace(/_/g, ' ').toLowerCase()}</span>)}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </LibraryPage>
  );
}
