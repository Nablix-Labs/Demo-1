'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Brain, AlertOctagon } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { Toggle } from '@/components/nablix/SectionHeader';
import { api, type GlobalLibrary } from '@/lib/api';
import { cn } from '@/lib/utils';

const REL: Record<string, string> = {
  DIRECT_FAILURE: 'bg-danger/10 text-danger',
  UNDERLYING_GAP: 'bg-highlight-amber/12 text-action-orange',
  AFFECTED_SKILL: 'bg-learning-blue/12 text-learning-blue',
};

export default function GlobalMisconc() {
  const [lib, setLib] = useState<GlobalLibrary | null>(null);
  useEffect(() => { api.getLibrary().then(setLib); }, []);

  return (
    <LibraryPage
      crumb="Misconceptions"
      eyebrow="Library · Errors & Misconceptions"
      title="Misconception Library"
      description="Reusable error types and the misconceptions behind them, across every topic."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Misconception</button>}
    >
      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        {/* Error types */}
        <section className="h-fit overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
          <div className="flex items-center gap-2 border-b border-muted-gray/70 px-5 py-3">
            <AlertOctagon className="h-4 w-4 text-learning-blue" />
            <h2 className="font-display text-base font-bold text-focus-navy">Error Types</h2>
          </div>
          <ul className="divide-y divide-muted-gray/50">
            {(lib?.error_types ?? []).map((e) => (
              <li key={e.error_code} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-2xs font-bold text-focus-navy">{e.error_code}</span>
                  <span className={cn('rounded px-1.5 py-0.5 text-2xs font-bold', e.severity === 'HIGH' ? 'bg-danger/10 text-danger' : 'bg-highlight-amber/12 text-action-orange')}>{e.severity}</span>
                </div>
                <div className="mt-0.5 text-sm font-semibold text-ink">{e.error_name}</div>
                <p className="text-xs text-slate-blue">{e.description}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Misconceptions */}
        <section className="h-fit overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
          <div className="flex items-center gap-2 border-b border-muted-gray/70 px-5 py-3">
            <Brain className="h-4 w-4 text-learning-blue" />
            <h2 className="font-display text-base font-bold text-focus-navy">Misconceptions</h2>
          </div>
          <ul className="divide-y divide-muted-gray/50">
            {(lib?.misconceptions ?? []).map((m) => (
              <li key={m.misconception_id} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <Link href={`/topics/${m.topic_id}/misconceptions`}><TopicTag code={m.topic_code} /></Link>
                  <h3 className="text-sm font-bold text-focus-navy">{m.name}</h3>
                  <Toggle on={m.active} />
                </div>
                <p className="mt-1 text-xs text-slate-blue">{m.description}</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {m.error_links.map((c) => <span key={c} className="rounded bg-reading-surface px-1.5 py-0.5 font-mono text-2xs font-semibold text-focus-navy ring-1 ring-inset ring-muted-gray/70">{c}</span>)}
                  {m.skill_links.map((s) => <span key={s.micro_skill_id} className={cn('rounded px-1.5 py-0.5 text-2xs font-semibold', REL[s.relationship_type])}>{s.micro_skill_id.split('.').pop()} · {s.relationship_type.replace('_', ' ').toLowerCase()}</span>)}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </LibraryPage>
  );
}
