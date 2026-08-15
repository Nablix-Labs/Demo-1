'use client';

/**
 * Worked Examples — v3 page 07. Selecting an example replaces its steps and
 * micro-skill mappings with that example's own children; examples are never
 * merged by matching title text (guide §7.2). Steps render in step_no order.
 */
import { useEffect, useState } from 'react';
import { FlaskConical, Plus, ListOrdered, Target } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta, WeightChip } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { WorkedExamplesData } from '@/lib/api/v3-contracts';
import { useSelectionOverride } from '@/lib/use-selection-override';
import { cn } from '@/lib/utils';

export default function WorkedExamplesPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const override = useSelectionOverride();
  const [data, setData] = useState<WorkedExamplesData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getWorkedExamples(topicId).then((d) => {
      setData(d);
      const named = override.select && d.hierarchy.worked_examples.some((n) => n.worked_example_id === override.select);
      setSelected(named ? override.select! : d.default_selection.worked_example_id);
    });
  }, [topicId, override.select]);

  if (!data) return <SectionLoading />;

  const examples = data.hierarchy.worked_examples;
  const node = examples.find((e) => e.worked_example_id === selected) ?? null;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Worked Examples"
        icon={<FlaskConical className="h-3.5 w-3.5" />}
        title="Worked Examples"
        description="Modelled solutions the tutor walks through, step by step."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Worked Example
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <section className="sheet overflow-hidden self-start">
          <CardHeader icon={<FlaskConical className="h-4 w-4" />} title={`Examples · ${examples.length}`} />
          <ul>
            {examples.map((e) => {
              const active = e.worked_example_id === selected;
              return (
                <li key={e.worked_example_id}>
                  <button
                    onClick={() => setSelected(e.worked_example_id)}
                    className={cn(
                      'flex w-full items-start gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                      active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className={cn('block truncate text-sm font-semibold', active ? 'text-white' : 'text-focus-navy')}>
                        {e.label}
                      </span>
                      <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                        {e.children.steps.length} steps · {e.children.micro_skill_mappings.length} mappings
                      </span>
                    </span>
                    <HealthBadge health={e.content_health} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        {node && (
          <div className="min-w-0 space-y-4">
            <HealthIssues health={node.content_health} />

            <section className="sheet overflow-hidden">
              <CardHeader
                icon={<FlaskConical className="h-4 w-4" />}
                title={node.details.title}
                action={<StatusPill status={node.details.status} />}
              />
              <div className="px-5 py-4">
                <Meta label="Problem" value={node.details.problem_statement} />
                <Meta label="Final answer" value={node.details.final_answer} />
                <Meta label="Phase" value={node.details.phase} />
                <Meta label="Version" value={node.details.version} />
              </div>
            </section>

            <section className="sheet overflow-hidden">
              <CardHeader icon={<ListOrdered className="h-4 w-4" />} title={`Steps · ${node.children.steps.length}`} />
              {node.children.steps.length === 0 ? (
                <div className="px-5 py-6 text-center text-sm font-semibold text-danger">
                  This example has no steps — that blocks review.
                </div>
              ) : (
                <ol>
                  {node.children.steps.map((s) => (
                    <li key={s.worked_example_step_id} className="flex gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                        {s.step_no}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-ink">{s.screen_content}</p>
                        <p className="mt-1 text-xs text-slate-blue">{s.narration_text}</p>
                        {(s.must_show || s.must_not_show) && (
                          <div className="mt-1.5 flex flex-wrap gap-2 text-2xs">
                            {s.must_show && (
                              <span className="rounded bg-success-sage/15 px-1.5 py-0.5 text-[#5c6b58]">
                                must show: {s.must_show}
                              </span>
                            )}
                            {s.must_not_show && (
                              <span className="rounded bg-danger/10 px-1.5 py-0.5 text-danger">
                                must not: {s.must_not_show}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>

            <section className="sheet overflow-hidden">
              <CardHeader
                icon={<Target className="h-4 w-4" />}
                title={`Micro-skill Mappings · ${node.children.micro_skill_mappings.length}`}
              />
              <div className="flex flex-wrap gap-3 px-5 py-4">
                {node.children.micro_skill_mappings.length === 0 ? (
                  <span className="text-sm font-semibold text-danger">No micro-skill mapping — that blocks review.</span>
                ) : (
                  node.children.micro_skill_mappings.map((m) => (
                    <span key={m.micro_skill_id} className="flex items-center gap-2">
                      <span className="text-sm text-ink">{m.skill_name}</span>
                      <WeightChip weight={m.weight} primary={m.is_primary} />
                    </span>
                  ))
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
