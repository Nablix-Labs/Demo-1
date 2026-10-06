'use client';

import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { loadHints } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';

export default function HintsPage() {
  const { data, error } = useLibrary(loadHints);
  const rows = data?.rows ?? null;

  return (
    <LibraryPage
      crumb="Hints"
      eyebrow="Library · Hints"
      title="Hint Library"
      description="Every hint across topics, with the misconceptions it supports. Open a topic to review its hints in context."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <ul className="divide-y divide-muted-gray/50">
          {rows === null ? (
            !error && Array.from({ length: 4 }).map((_, i) => <li key={i} className="px-5 py-3"><div className="h-6 animate-pulse rounded bg-reading-surface" /></li>)
          ) : rows.length === 0 ? (
            <li className="px-5 py-6 text-sm text-slate-blue">No hints in live content.</li>
          ) : rows.map((h) => (
            <li key={`${h.topic_id}-${h.id}`} className="flex items-start gap-3 px-5 py-3 hover:bg-reading-surface">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-2xs font-bold text-focus-navy">{h.label}</span>
                  <span className="font-mono text-2xs text-slate-blue/70">{h.id}</span>
                </div>
                <p className="mt-0.5 text-sm text-ink">{h.preview}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-2xs text-slate-blue">
                  <TopicTag code={h.topic_code} title={h.topic_title} href={`/topics/${h.topic_id}/hints-cues`} />
                  {h.misconceptions.map((m) => (
                    <span key={m} className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">{m}</span>
                  ))}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <RowHealth health={h.content_health} />
                <StatusPill status={h.active ? 'ACTIVE' : 'INACTIVE'} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </LibraryPage>
  );
}
