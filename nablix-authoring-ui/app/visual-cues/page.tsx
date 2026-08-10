'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Image as ImageIcon } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { api, type LibVisualCue } from '@/lib/api';

export default function VisualCuesPage() {
  const [rows, setRows] = useState<LibVisualCue[] | null>(null);
  useEffect(() => { api.getLibrary().then((l) => setRows(l.visual_cues)); }, []);

  return (
    <LibraryPage
      crumb="Visual Cues"
      eyebrow="Library · Visual Cues"
      title="Visual Cue Library"
      description="Visual cues with retrieval metadata and review status, across every topic."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Visual Cue</button>}
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows === null
          ? Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-card bg-white/50" />)
          : rows.map((c) => (
            <section key={c.visual_cue_id} className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
              <div className="flex h-28 items-center justify-center bg-gradient-to-br from-focus-navy/90 to-slate-blue/80 text-white/70">
                <ImageIcon className="h-8 w-8" />
              </div>
              <div className="p-3">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-bold text-focus-navy">{c.cue_name}</h3>
                  <StatusPill status={c.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-slate-blue">{c.cue_purpose}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.retrieval_keywords.slice(0, 3).map((k) => <span key={k} className="rounded bg-reading-surface px-1.5 py-0.5 text-2xs text-slate-blue ring-1 ring-inset ring-muted-gray/70">{k}</span>)}
                </div>
                <div className="mt-2 flex items-center justify-between border-t border-muted-gray/50 pt-2 text-2xs">
                  <Link href={`/topics/${c.topic_id}/hints-cues`}><TopicTag code={c.topic_code} /></Link>
                  <span className="font-mono text-slate-blue/70">review: {c.review_status}</span>
                </div>
              </div>
            </section>
          ))}
      </div>
    </LibraryPage>
  );
}
