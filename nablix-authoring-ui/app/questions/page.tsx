'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { QUESTION_PHASES, loadQuestions } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';
import { cn } from '@/lib/utils';

const CHIP = 'rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70';

export default function GlobalQuestions() {
  const { data, error } = useLibrary(loadQuestions);
  const rows = data?.rows ?? null;
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('All');

  // Difficulty chips come from the levels the questions actually carry.
  const filters = useMemo(() => {
    const levels = [...new Set((rows ?? []).map((r) => r.difficulty))].filter((d) => d != null).sort((a, b) => a - b);
    return ['All', ...QUESTION_PHASES.map((p) => p.label), ...levels.map((d) => `Difficulty ${d}`)];
  }, [rows]);

  const filtered = useMemo(() => (rows ?? []).filter((r) => {
    const text = `${r.label} ${r.question_id}`.toLowerCase().includes(q.toLowerCase());
    const f =
      filter === 'All' ? true :
      filter.startsWith('Phase') ? QUESTION_PHASES.find((p) => p.label === filter)?.id === r.phase_id :
      filter.startsWith('Difficulty') ? `Difficulty ${r.difficulty}` === filter : true;
    return text && f;
  }), [rows, q, filter]);

  return (
    <LibraryPage
      crumb="Questions"
      eyebrow="Library · Question Bank"
      title="Question Bank"
      description="Every question across topics and phases, filterable by phase and difficulty."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="flex flex-wrap items-center gap-2 border-b border-muted-gray/70 px-4 py-3">
          <div className="flex flex-1 items-center gap-2">
            <Search className="h-4 w-4 text-slate-blue" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search questions…" className="w-full min-w-[140px] bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none" />
          </div>
          <div className="flex flex-wrap gap-1">
            {filters.map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={cn('rounded-pill px-2.5 py-1 text-2xs font-semibold transition-colors', filter === f ? 'bg-focus-navy text-white' : 'text-slate-blue hover:bg-reading-surface')}>{f}</button>
            ))}
          </div>
          <span className="text-2xs font-semibold text-slate-blue">{filtered.length} of {rows?.length ?? 0}</span>
        </div>
        <ul className="divide-y divide-muted-gray/50">
          {rows === null ? (
            !error && Array.from({ length: 4 }).map((_, i) => <li key={i} className="px-4 py-3"><div className="h-6 animate-pulse rounded bg-reading-surface" /></li>)
          ) : filtered.length === 0 ? (
            <li className="px-4 py-6 text-sm text-slate-blue">{rows.length ? 'No questions match.' : 'No questions in live content.'}</li>
          ) : filtered.map((r) => (
            <li key={`${r.topic_id}-${r.phase_id}-${r.question_id}`} className="px-4 py-3 hover:bg-reading-surface">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-ink">{r.label}</p>
                <RowHealth health={r.content_health} />
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-2xs text-slate-blue">
                <TopicTag code={r.topic_code} title={r.topic_title} href={`/topics/${r.topic_id}/questions`} />
                <span className="font-mono">{r.question_id}</span>
                <span className={CHIP}>{r.phase_label}</span>
                <span className={CHIP}>{r.question_type}</span>
                <span className={CHIP}>{r.question_role}</span>
                <span className={CHIP}>Difficulty {r.difficulty}</span>
                {r.child_counts && (
                  <span className="text-slate-blue/70">
                    {r.child_counts.micro_skill_mappings} skill maps · {r.child_counts.answer_specification} answer spec · {r.child_counts.error_mappings} error maps
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </LibraryPage>
  );
}
