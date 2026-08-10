'use client';

import { Target, Plus, ArrowRight } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { SectionHeader, SectionLoading } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { CoverageBadge } from '@/components/nablix/CoverageBadge';
import { cn } from '@/lib/utils';

const PRIORITY: Record<string, string> = {
  HIGH: 'bg-action-orange/12 text-action-orange',
  MEDIUM: 'bg-learning-blue/12 text-learning-blue',
  LOW: 'bg-slate-blue/10 text-slate-blue',
};

export default function MicroSkillsPage() {
  const c = useContent();
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Micro-skills"
        icon={<Target className="h-3.5 w-3.5" />}
        title="Micro-skills"
        description="The atomic skills a student must master. Each shows coverage across Diagnostic, Worked, Guided, Independent and Rescue."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Micro-skill
          </button>
        }
      />

      <div className="grid gap-3">
        {c.micro_skills.map((m) => (
          <section key={m.micro_skill_id} className="sheet p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-focus-navy px-1.5 py-0.5 font-mono text-2xs font-bold text-white">{m.skill_code}</span>
                  <h3 className="font-display text-base font-bold text-focus-navy">{m.skill_name}</h3>
                  <StatusPill status={m.status} />
                </div>
                <p className="mt-1 max-w-2xl text-sm text-slate-blue">{m.description}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 font-mono text-2xs text-slate-blue/80">
                  <span>{m.micro_skill_id}</span>
                  {m.prerequisite && (
                    <span className="flex items-center gap-1">
                      <ArrowRight className="h-3 w-3" /> requires {m.prerequisite}
                    </span>
                  )}
                </div>
              </div>
              <span className={cn('rounded-pill px-2.5 py-1 text-2xs font-bold uppercase tracking-wide', PRIORITY[m.assessment_priority])}>
                {m.assessment_priority} priority
              </span>
            </div>

            <div className="mt-3 grid grid-cols-5 gap-2 border-t border-muted-gray/60 pt-3">
              {(
                [
                  ['Diagnostic', m.diagnostic],
                  ['Worked', m.worked],
                  ['Guided', m.guided],
                  ['Independent', m.independent],
                  ['Hints', m.hints],
                ] as const
              ).map(([label, n]) => (
                <div key={label} className="flex flex-col items-center gap-1 rounded-lg bg-reading-surface py-2">
                  <CoverageBadge state={n === 0 ? 'missing' : n === 1 ? 'warn' : 'ok'} count={n} />
                  <span className="text-2xs font-semibold text-slate-blue">{label}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
