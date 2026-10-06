'use client';

import { Image as ImageIcon } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { loadVisualCues } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';

export default function VisualCuesPage() {
  const { data, error } = useLibrary(loadVisualCues);
  const rows = data?.rows ?? null;

  return (
    <LibraryPage
      crumb="Visual Cues"
      eyebrow="Library · Visual Cues"
      title="Visual Cue Library"
      description="Every visual cue across topics, with the misconceptions it supports and its content health."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows === null
          ? !error && Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-card bg-white/50" />)
          : rows.length === 0
            ? <p className="text-sm text-slate-blue">No visual cues in live content.</p>
            : rows.map((c) => (
              <section key={`${c.topic_id}-${c.id}`} className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
                <div className="flex h-28 items-center justify-center bg-gradient-to-br from-focus-navy/90 to-slate-blue/80 text-white/70">
                  <ImageIcon className="h-8 w-8" />
                </div>
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-bold text-focus-navy">{c.label}</h3>
                    <StatusPill status={c.active ? 'ACTIVE' : 'INACTIVE'} />
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-blue">{c.preview}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.misconceptions.map((m) => <span key={m} className="rounded bg-reading-surface px-1.5 py-0.5 text-2xs text-slate-blue ring-1 ring-inset ring-muted-gray/70">{m}</span>)}
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2 border-t border-muted-gray/50 pt-2 text-2xs">
                    <TopicTag code={c.topic_code} title={c.topic_title} href={`/topics/${c.topic_id}/hints-cues`} />
                    <div className="flex items-center gap-2">
                      {c.shared_by_misconception_count !== undefined && (
                        <span className="text-slate-blue/70">shared by {c.shared_by_misconception_count}</span>
                      )}
                      <RowHealth health={c.content_health} />
                    </div>
                  </div>
                </div>
              </section>
            ))}
      </div>
    </LibraryPage>
  );
}
