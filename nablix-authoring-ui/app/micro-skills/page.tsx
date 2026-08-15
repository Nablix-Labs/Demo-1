'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Plus, Search } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { CoverageBadge } from '@/components/nablix/CoverageBadge';
import { api, type LibMicroSkill } from '@/lib/api';
import { cn } from '@/lib/utils';

const PRIORITY: Record<string, string> = {
  HIGH: 'bg-action-orange/12 text-action-orange',
  MEDIUM: 'bg-learning-blue/12 text-learning-blue',
  LOW: 'bg-slate-blue/10 text-slate-blue',
};

export default function GlobalMicroSkills() {
  const [rows, setRows] = useState<LibMicroSkill[] | null>(null);
  const [q, setQ] = useState('');
  useEffect(() => { api.getLibrary().then((l) => setRows(l.micro_skills)); }, []);

  const filtered = useMemo(
    () => (rows ?? []).filter((r) => `${r.skill_code} ${r.skill_name} ${r.micro_skill_id}`.toLowerCase().includes(q.toLowerCase())),
    [rows, q],
  );

  return (
    <LibraryPage
      crumb="Micro-skills"
      eyebrow="Library · Cross-topic"
      title="Micro-skill Library"
      description="Every micro-skill across the curriculum with priority, prerequisites and coverage."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Micro-skill</button>}
    >
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="flex items-center gap-2 border-b border-muted-gray/70 px-4 py-3">
          <Search className="h-4 w-4 text-slate-blue" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search micro-skills…" className="w-full bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none" />
          <span className="text-2xs font-semibold text-slate-blue">{filtered.length} of {rows?.length ?? 0}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-muted-gray/70 text-left text-2xs uppercase tracking-wide text-slate-blue">
                <th className="px-4 py-2.5 font-bold">Topic</th>
                <th className="px-3 py-2.5 font-bold">ID</th>
                <th className="px-3 py-2.5 font-bold">Skill</th>
                <th className="px-3 py-2.5 font-bold">Priority</th>
                <th className="px-3 py-2.5 text-center font-bold">Diag</th>
                <th className="px-3 py-2.5 text-center font-bold">Guided</th>
                <th className="px-3 py-2.5 text-center font-bold">Indep</th>
                <th className="px-3 py-2.5 font-bold">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows === null ? (
                Array.from({ length: 5 }).map((_, i) => <tr key={i} className="border-b border-muted-gray/50"><td colSpan={8} className="px-4 py-3"><div className="h-5 animate-pulse rounded bg-reading-surface" /></td></tr>)
              ) : filtered.map((m) => (
                <tr key={m.micro_skill_id} className="border-b border-muted-gray/50 last:border-0 hover:bg-reading-surface">
                  <td className="px-4 py-2.5"><Link href={`/topics/${m.topic_id}/micro-skills`}><TopicTag code={m.topic_code} /></Link></td>
                  <td className="px-3 py-2.5 font-mono text-2xs text-slate-blue">{m.micro_skill_id}</td>
                  <td className="px-3 py-2.5"><span className="font-semibold text-focus-navy">{m.skill_name}</span></td>
                  <td className="px-3 py-2.5"><span className={cn('rounded px-1.5 py-0.5 text-2xs font-bold', PRIORITY[m.assessment_priority])}>{m.assessment_priority}</span></td>
                  <td className="px-3 py-2.5 text-center"><CoverageBadge state={m.diagnostic ? 'ok' : 'missing'} count={m.diagnostic} /></td>
                  <td className="px-3 py-2.5 text-center"><CoverageBadge state={m.guided ? 'ok' : 'missing'} count={m.guided} /></td>
                  <td className="px-3 py-2.5 text-center"><CoverageBadge state={m.independent > 1 ? 'ok' : m.independent === 1 ? 'warn' : 'missing'} count={m.independent} /></td>
                  <td className="px-3 py-2.5"><StatusPill status={m.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </LibraryPage>
  );
}
