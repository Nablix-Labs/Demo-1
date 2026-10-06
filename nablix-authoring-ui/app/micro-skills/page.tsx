'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth, TopicTag } from '@/components/nablix/LibraryPage';
import { loadMicroSkills } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';
import { cn } from '@/lib/utils';

/** coverage_counts keys shown as columns. Counts are the backend's; whether a
 *  count is enough is its content_health, not a threshold applied here. */
const COUNTS: { key: string; label: string }[] = [
  { key: 'diagnostic', label: 'Diag' },
  { key: 'guided', label: 'Guided' },
  { key: 'independent', label: 'Indep' },
  { key: 'misconceptions', label: 'Misc' },
  { key: 'hints', label: 'Hints' },
  { key: 'scaffolds', label: 'Scaff' },
];

export default function GlobalMicroSkills() {
  const { data, error } = useLibrary(loadMicroSkills);
  const rows = data?.rows ?? null;
  const [q, setQ] = useState('');

  const filtered = useMemo(
    () => (rows ?? []).filter((r) => `${r.label} ${r.micro_skill_id} ${r.topic_code}`.toLowerCase().includes(q.toLowerCase())),
    [rows, q],
  );

  return (
    <LibraryPage
      crumb="Micro-skills"
      eyebrow="Library · Cross-topic"
      title="Micro-skill Library"
      description="Every micro-skill across the curriculum with its content counts and health."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="flex items-center gap-2 border-b border-muted-gray/70 px-4 py-3">
          <Search className="h-4 w-4 text-slate-blue" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search micro-skills…" className="w-full bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none" />
          <span className="shrink-0 text-2xs font-semibold text-slate-blue">{filtered.length} of {rows?.length ?? 0}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-muted-gray/70 text-left text-2xs uppercase tracking-wide text-slate-blue">
                <th className="px-4 py-2.5 font-bold">Topic</th>
                <th className="px-3 py-2.5 font-bold">ID</th>
                <th className="px-3 py-2.5 font-bold">Skill</th>
                {COUNTS.map((c) => <th key={c.key} className="px-3 py-2.5 text-center font-bold">{c.label}</th>)}
                <th className="px-3 py-2.5 font-bold">Health</th>
              </tr>
            </thead>
            <tbody>
              {rows === null ? (
                !error && Array.from({ length: 5 }).map((_, i) => <tr key={i} className="border-b border-muted-gray/50"><td colSpan={COUNTS.length + 4} className="px-4 py-3"><div className="h-5 animate-pulse rounded bg-reading-surface" /></td></tr>)
              ) : filtered.length === 0 ? (
                <tr><td colSpan={COUNTS.length + 4} className="px-4 py-6 text-sm text-slate-blue">{rows.length ? 'No micro-skills match.' : 'No micro-skills in live content.'}</td></tr>
              ) : filtered.map((m) => (
                <tr key={`${m.topic_id}-${m.micro_skill_id}`} className="border-b border-muted-gray/50 last:border-0 hover:bg-reading-surface">
                  <td className="px-4 py-2.5"><TopicTag code={m.topic_code} title={m.topic_title} href={`/topics/${m.topic_id}/micro-skills`} /></td>
                  <td className="px-3 py-2.5 font-mono text-2xs text-slate-blue">{m.micro_skill_id}</td>
                  <td className="px-3 py-2.5"><span className="font-semibold text-focus-navy">{m.label}</span></td>
                  {COUNTS.map((c) => {
                    const n = m.coverage_counts?.[c.key];
                    return (
                      <td key={c.key} className={cn('px-3 py-2.5 text-center font-mono text-xs tabular-nums', n ? 'text-ink' : 'text-slate-blue/50')}>
                        {n ?? '—'}
                      </td>
                    );
                  })}
                  <td className="px-3 py-2.5"><RowHealth health={m.content_health} showLabel /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </LibraryPage>
  );
}
