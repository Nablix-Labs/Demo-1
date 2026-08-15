'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Layers, ArrowRight } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { Toggle } from '@/components/nablix/SectionHeader';
import { api, type LibScaffold } from '@/lib/api';

export default function GlobalScaffolds() {
  const [rows, setRows] = useState<LibScaffold[] | null>(null);
  useEffect(() => { api.getLibrary().then((l) => setRows(l.scaffolds)); }, []);

  return (
    <LibraryPage
      crumb="Scaffolds"
      eyebrow="Library · Scaffolds"
      title="Scaffold Library"
      description="Step-by-step recovery routes across topics, with their stages and completion rules."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Scaffold</button>}
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {rows === null
          ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-48 animate-pulse rounded-card bg-white/50" />)
          : rows.map((s) => (
            <section key={s.scaffold_id} className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
              <div className="flex items-center justify-between gap-2 border-b border-muted-gray/70 px-5 py-3">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-learning-blue" />
                  <h3 className="font-display text-sm font-bold text-focus-navy">{s.scaffold_name}</h3>
                </div>
                <div className="flex items-center gap-2">
                  <Link href={`/topics/${s.topic_id}/scaffolds`}><TopicTag code={s.topic_code} /></Link>
                  <Toggle on={s.active} />
                </div>
              </div>
              <div className="px-5 py-3">
                <p className="text-xs text-slate-blue"><span className="font-semibold">Trigger · </span>{s.trigger_rule}</p>
                <ol className="mt-2 space-y-1.5">
                  {s.steps.map((st) => (
                    <li key={st.stage_no} className="flex items-center gap-2 rounded-lg bg-reading-surface px-3 py-2 text-xs">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">{st.stage_no}</span>
                      <span className="min-w-0 flex-1 truncate text-ink">{st.prompt}</span>
                      <ArrowRight className="h-3 w-3 text-slate-blue/50" />
                      <span className="font-mono text-2xs text-slate-blue">{st.next_on_correct}</span>
                    </li>
                  ))}
                </ol>
              </div>
            </section>
          ))}
      </div>
    </LibraryPage>
  );
}
