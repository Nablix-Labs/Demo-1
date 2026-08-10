'use client';

import { useEffect, useState } from 'react';
import { FlaskConical, Plus, Eye, EyeOff, Target } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, Meta, WeightChip, SectionLoading, MoveControls } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { moveItem } from '@/lib/utils';
import type { WorkedExample } from '@/lib/api/contracts';

export default function WorkedExamplesPage() {
  const c = useContent();
  const [examples, setExamples] = useState<WorkedExample[]>([]);
  useEffect(() => {
    if (c) setExamples(c.worked_examples);
  }, [c]);
  const moveStep = (id: string, i: number, dir: -1 | 1) =>
    setExamples((exs) => exs.map((e) => (e.worked_example_id === id ? { ...e, steps: moveItem(e.steps, i, dir) } : e)));
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Worked Examples"
        icon={<FlaskConical className="h-3.5 w-3.5" />}
        title="Worked Examples"
        description="Fully demonstrated problems. Each needs at least one step and one micro-skill mapping before it can be submitted."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> New Worked Example
          </button>
        }
      />

      {examples.map((we) => (
        <div key={we.worked_example_id} className="space-y-4">
          <section className="sheet">
            <CardHeader
              icon={<FlaskConical className="h-4 w-4" />}
              title={we.title}
              action={<StatusPill status={we.status} />}
            />
            <div className="px-5 py-3">
              <Meta label="Problem" value={we.problem_statement} />
              <Meta label="Final Answer" value={<span className="font-mono">{we.final_answer}</span>} />
              <Meta label="Phase" value={<span className="font-mono text-xs">PHASE_1_ORIENTATION</span>} />
            </div>
          </section>

          {/* Steps */}
          <section className="sheet overflow-hidden">
            <CardHeader title={`Steps · ${we.steps.length}`} />
            <ol>
              {we.steps.map((s, i) => (
                <li key={s.step_no} className="flex gap-3 border-b border-muted-gray/50 px-4 py-3 last:border-0">
                  <div className="flex flex-col items-center gap-1 pt-0.5">
                    <MoveControls
                      onUp={() => moveStep(we.worked_example_id, i, -1)}
                      onDown={() => moveStep(we.worked_example_id, i, 1)}
                      canUp={i > 0}
                      canDown={i < we.steps.length - 1}
                    />
                    <span className="font-mono text-2xs font-bold text-slate-blue">{i + 1}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="rounded-md bg-reading-surface px-3 py-2 font-mono text-sm text-focus-navy">{s.screen_content}</div>
                    <p className="mt-1.5 text-xs text-slate-blue">{s.narration_text}</p>
                    <div className="mt-1.5 flex flex-wrap gap-3 text-2xs">
                      {s.must_show && (
                        <span className="flex items-center gap-1 text-[#5c6b58]">
                          <Eye className="h-3 w-3" /> must show: {s.must_show}
                        </span>
                      )}
                      {s.must_not_show && (
                        <span className="flex items-center gap-1 text-danger">
                          <EyeOff className="h-3 w-3" /> must not show: {s.must_not_show}
                        </span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          {/* Skill mappings */}
          <section className="sheet overflow-hidden">
            <CardHeader icon={<Target className="h-4 w-4" />} title="Micro-skill Mappings" />
            <ul className="divide-y divide-muted-gray/50">
              {we.skill_mappings.map((m) => (
                <li key={m.micro_skill_id} className="flex items-center justify-between px-5 py-2.5">
                  <span className="font-mono text-xs font-semibold text-focus-navy">{m.micro_skill_id}</span>
                  <WeightChip weight={m.weight} primary={m.is_primary} />
                </li>
              ))}
            </ul>
          </section>
        </div>
      ))}
    </div>
  );
}
