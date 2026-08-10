'use client';

import { AlertOctagon, Plus, Brain, Link2 } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, Toggle, SectionLoading } from '@/components/nablix/SectionHeader';
import { cn } from '@/lib/utils';

const REL: Record<string, string> = {
  DIRECT_FAILURE: 'bg-danger/10 text-danger',
  UNDERLYING_GAP: 'bg-highlight-amber/12 text-action-orange',
  AFFECTED_SKILL: 'bg-learning-blue/12 text-learning-blue',
};

export default function MisconceptionsPage() {
  const c = useContent();
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Errors & Misconceptions"
        icon={<AlertOctagon className="h-3.5 w-3.5" />}
        title="Errors & Misconceptions"
        description="An error is what was visibly wrong. A misconception is the likely wrong mental model behind it."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> New Misconception
          </button>
        }
      />

      {/* Error types */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<AlertOctagon className="h-4 w-4" />} title={`Error Types · ${c.error_types.length}`} />
        <ul>
          {c.error_types.map((e) => (
            <li key={e.error_code} className="flex items-start justify-between gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-2xs font-bold text-focus-navy">{e.error_code}</span>
                  <span
                    className={cn(
                      'rounded px-1.5 py-0.5 text-2xs font-bold',
                      e.severity === 'HIGH' ? 'bg-danger/10 text-danger' : 'bg-highlight-amber/12 text-action-orange',
                    )}
                  >
                    {e.severity}
                  </span>
                </div>
                <div className="mt-0.5 text-sm font-semibold text-ink">{e.error_name}</div>
                <p className="text-xs text-slate-blue">{e.description}</p>
                <div className="mt-1 font-mono text-2xs text-slate-blue/70">detect: {e.detection_method}</div>
              </div>
              <Toggle on={e.active} />
            </li>
          ))}
        </ul>
      </section>

      {/* Misconceptions */}
      {c.misconceptions.map((m) => (
        <section key={m.misconception_id} className="sheet">
          <CardHeader
            icon={<Brain className="h-4 w-4" />}
            title={m.name}
            action={<Toggle on={m.active} />}
          />
          <div className="space-y-3 px-5 py-3">
            <p className="text-sm text-ink">{m.description}</p>
            <div className="rounded-lg bg-reading-surface px-3 py-2 text-xs text-slate-blue">
              <span className="font-semibold text-slate-blue">Diagnosis rule · </span>
              {m.diagnosis_rule}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="mb-1.5 flex items-center gap-1 text-2xs font-bold uppercase tracking-wide text-slate-blue">
                  <Link2 className="h-3 w-3" /> Linked errors
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {m.error_links.map((code) => (
                    <span key={code} className="rounded-md bg-white px-2 py-0.5 font-mono text-2xs font-semibold text-focus-navy ring-1 ring-inset ring-muted-gray/70">
                      {code}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1.5 flex items-center gap-1 text-2xs font-bold uppercase tracking-wide text-slate-blue">
                  <Link2 className="h-3 w-3" /> Affected micro-skills
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {m.skill_links.map((s) => (
                    <span key={s.micro_skill_id} className={cn('flex items-center gap-1 rounded-md px-2 py-0.5 text-2xs font-semibold', REL[s.relationship_type])}>
                      <span className="font-mono">{s.micro_skill_id.split('.').pop()}</span>
                      {s.relationship_type.replace('_', ' ').toLowerCase()}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
