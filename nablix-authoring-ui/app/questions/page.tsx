'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Plus, Search } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { api, type LibQuestion, type Phase } from '@/lib/api';
import { cn } from '@/lib/utils';

const PHASE_LABEL: Record<Phase, string> = {
  PHASE_0_DIAGNOSTIC: 'Phase 0',
  PHASE_2_GUIDED_LEARNING: 'Phase 2',
  PHASE_3_INDEPENDENT_PRACTICE: 'Phase 3',
};
const FILTERS = ['All', 'Phase 0', 'Phase 2', 'Phase 3', 'Difficulty 1', 'Difficulty 2', 'Draft'];

export default function GlobalQuestions() {
  const [rows, setRows] = useState<LibQuestion[] | null>(null);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('All');
  useEffect(() => { api.getLibrary().then((l) => setRows(l.questions)); }, []);

  const filtered = useMemo(() => (rows ?? []).filter((r) => {
    const text = `${r.question_text} ${r.question_id} ${r.item_family_id}`.toLowerCase().includes(q.toLowerCase());
    const f =
      filter === 'All' ? true :
      filter.startsWith('Phase') ? PHASE_LABEL[r.phase] === filter :
      filter === 'Difficulty 1' ? r.difficulty === 1 :
      filter === 'Difficulty 2' ? r.difficulty === 2 :
      filter === 'Draft' ? r.status === 'DRAFT' : true;
    return text && f;
  }), [rows, q, filter]);

  return (
    <LibraryPage
      crumb="Questions"
      eyebrow="Library · Question Bank"
      title="Question Bank"
      description="Every question across topics, filterable by phase, type and difficulty."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Question</button>}
    >
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="flex flex-wrap items-center gap-2 border-b border-muted-gray/70 px-4 py-3">
          <div className="flex flex-1 items-center gap-2">
            <Search className="h-4 w-4 text-slate-blue" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search questions…" className="w-full min-w-[140px] bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none" />
          </div>
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={cn('rounded-pill px-2.5 py-1 text-2xs font-semibold transition-colors', filter === f ? 'bg-focus-navy text-white' : 'text-slate-blue hover:bg-reading-surface')}>{f}</button>
            ))}
          </div>
        </div>
        <ul className="divide-y divide-muted-gray/50">
          {rows === null ? (
            Array.from({ length: 4 }).map((_, i) => <li key={i} className="px-4 py-3"><div className="h-6 animate-pulse rounded bg-reading-surface" /></li>)
          ) : filtered.map((r) => (
            <li key={r.question_id} className="px-4 py-3 hover:bg-reading-surface">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-ink">{r.question_text}</p>
                <StatusPill status={r.status} />
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-2xs text-slate-blue">
                <Link href={`/topics/${r.topic_id}/questions`}><TopicTag code={r.topic_code} /></Link>
                <span className="font-mono">{r.question_id}</span>
                <span className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">{PHASE_LABEL[r.phase]}</span>
                <span className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">{r.question_type}</span>
                <span className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">Difficulty {r.difficulty}</span>
                <span className="font-mono text-slate-blue/70">{r.item_family_id}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </LibraryPage>
  );
}
