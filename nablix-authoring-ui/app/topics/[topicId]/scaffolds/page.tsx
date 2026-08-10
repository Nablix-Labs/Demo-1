'use client';

import { useEffect, useState } from 'react';
import { Layers, Plus, ArrowRight, CornerDownRight, Copy } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, Meta, Toggle, SectionLoading, MoveControls } from '@/components/nablix/SectionHeader';
import { moveItem } from '@/lib/utils';
import type { Scaffold } from '@/lib/api/contracts';

export default function ScaffoldsPage() {
  const c = useContent();
  const [scaffolds, setScaffolds] = useState<Scaffold[]>([]);
  useEffect(() => {
    if (c) setScaffolds(c.scaffolds);
  }, [c]);
  const moveStage = (id: string, i: number, dir: -1 | 1) =>
    setScaffolds((xs) => xs.map((s) => (s.scaffold_id === id ? { ...s, steps: moveItem(s.steps, i, dir) } : s)));
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Scaffolds & Parallel Examples"
        icon={<Layers className="h-3.5 w-3.5" />}
        title="Scaffolds & Parallel Examples"
        description="Step-by-step recovery routes and fresh parallel problems that target a specific misconception."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> New Scaffold
          </button>
        }
      />

      {scaffolds.map((s) => (
        <section key={s.scaffold_id} className="sheet">
          <CardHeader icon={<Layers className="h-4 w-4" />} title={s.scaffold_name} action={<Toggle on={s.active} />} />
          <div className="px-5 py-3">
            <Meta label="Trigger" value={s.trigger_rule} />
            <Meta label="Completion" value={s.completion_rule} />
          </div>
          <div className="border-t border-muted-gray/60 px-4 py-3">
            <div className="mb-2 text-2xs font-bold uppercase tracking-wide text-slate-blue">Stages</div>
            <ol className="space-y-2">
              {s.steps.map((step, i) => (
                <li key={step.stage_no} className="rounded-lg border border-muted-gray/70 bg-white p-3">
                  <div className="flex items-center gap-2">
                    <MoveControls
                      onUp={() => moveStage(s.scaffold_id, i, -1)}
                      onDown={() => moveStage(s.scaffold_id, i, 1)}
                      canUp={i > 0}
                      canDown={i < s.steps.length - 1}
                    />
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                      {i + 1}
                    </span>
                    <p className="text-sm font-medium text-ink">{step.prompt}</p>
                  </div>
                  <div className="mt-2 grid gap-1.5 pl-8 text-2xs sm:grid-cols-2">
                    <div className="text-slate-blue">
                      expected: <span className="font-mono text-focus-navy">{step.expected_response}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                      <span className="flex items-center gap-1 text-[#5c6b58]">
                        <ArrowRight className="h-3 w-3" /> correct → <span className="font-mono">{step.next_on_correct}</span>
                      </span>
                      <span className="flex items-center gap-1 text-action-orange">
                        <CornerDownRight className="h-3 w-3" /> incorrect → <span className="font-mono">{step.next_on_incorrect}</span>
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>
      ))}

      {/* Parallel examples */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Copy className="h-4 w-4" />} title={`Parallel Examples · ${c.parallel_examples.length}`} />
        <ul>
          {c.parallel_examples.map((p) => (
            <li key={p.parallel_example_id} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-2xs font-bold text-learning-blue">{p.misconception_id}</span>
                <Toggle on={p.active} />
              </div>
              <p className="mt-1 text-sm text-ink">{p.problem_statement}</p>
              <div className="mt-0.5 font-mono text-xs text-slate-blue">answer: {p.final_answer}</div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
