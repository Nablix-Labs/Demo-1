'use client';

/**
 * Scaffolds & Parallel Examples — v3 page 13. Two tabs over different
 * hierarchies: Topic → Scaffold → steps/question links, and Misconception →
 * Parallel Examples. Switching tabs clears the other tab's editor state
 * (guide §10.1). Steps render in stage_no order.
 */
import { useEffect, useState } from 'react';
import { Layers, Plus, ListOrdered, Link2, Copy } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { ScaffoldsData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

export default function ScaffoldsPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<ScaffoldsData | null>(null);
  const [tab, setTab] = useState<string>('SCAFFOLDS');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getScaffolds(topicId).then((d) => {
      setData(d);
      setTab(d.default_selection.tab_id);
      setSelected(d.default_selection.scaffold_id);
    });
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const scaffolds = data.hierarchy.scaffolds;
  const groups = data.hierarchy.parallel_examples_by_misconception;
  const isScaffoldTab = tab === data.tabs[0]?.tab_id;
  const node = isScaffoldTab ? scaffolds.find((s) => s.scaffold_id === selected) ?? null : null;

  function selectTab(next: string) {
    setTab(next);
    setSelected(next === data!.tabs[0]?.tab_id ? (scaffolds[0]?.scaffold_id ?? null) : null);
  }

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Scaffolds & Parallel Examples"
        icon={<Layers className="h-3.5 w-3.5" />}
        title="Scaffolds & Parallel Examples"
        description="Step-by-step rescue routes, and the fresh examples used to re-test a repaired misconception."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add {isScaffoldTab ? 'Scaffold' : 'Parallel Example'}
          </button>
        }
      />

      <div className="flex flex-wrap items-center gap-1 border-b border-muted-gray/70">
        {data.tabs.map((t) => (
          <button
            key={t.tab_id}
            onClick={() => selectTab(t.tab_id)}
            className={cn(
              'rounded-t-lg px-3 py-2 text-sm font-semibold',
              tab === t.tab_id ? 'bg-white text-focus-navy shadow-[inset_0_-2px_0_0_var(--lime)]' : 'text-slate-blue hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isScaffoldTab ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
          <section className="sheet overflow-hidden self-start">
            <CardHeader icon={<Layers className="h-4 w-4" />} title={`Scaffolds · ${scaffolds.length}`} />
            <ul>
              {scaffolds.map((s) => {
                const active = s.scaffold_id === selected;
                return (
                  <li key={s.scaffold_id}>
                    <button
                      onClick={() => setSelected(s.scaffold_id)}
                      className={cn(
                        'flex w-full items-start gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                        active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                      )}
                    >
                      <span className="min-w-0 flex-1">
                        <span className={cn('block truncate text-sm font-semibold', active ? 'text-white' : 'text-focus-navy')}>
                          {s.label}
                        </span>
                        <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                          {s.children.steps.length} stages · {s.children.question_links.length} questions
                        </span>
                      </span>
                      <HealthBadge health={s.content_health} />
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
                <CardHeader icon={<Layers className="h-4 w-4" />} title={node.details.scaffold_name} />
                <div className="px-5 py-4">
                  <Meta label="Trigger" value={node.details.trigger_rule} />
                  <Meta label="Completion" value={node.details.completion_rule} />
                  <Meta label="Active" value={node.details.active ? 'Yes' : 'No'} />
                </div>
              </section>

              <section className="sheet overflow-hidden">
                <CardHeader icon={<ListOrdered className="h-4 w-4" />} title={`Stages · ${node.children.steps.length}`} />
                {node.children.steps.length === 0 ? (
                  <div className="px-5 py-6 text-center text-sm font-semibold text-danger">
                    This scaffold has no stages — that blocks review.
                  </div>
                ) : (
                  <ol>
                    {node.children.steps.map((s) => (
                      <li key={s.scaffold_step_id} className="flex gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                          {s.stage_no}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-ink">{s.prompt}</p>
                          {s.partial_content && <p className="mt-1 text-xs text-slate-blue">{s.partial_content}</p>}
                          <p className="mt-1 text-2xs text-slate-blue">Expects: {s.expected_response}</p>
                          <div className="mt-1 flex flex-wrap gap-2 text-2xs">
                            <span className="rounded bg-success-sage/15 px-1.5 py-0.5 text-[#5c6b58]">
                              correct → {s.next_on_correct}
                            </span>
                            <span className="rounded bg-highlight-amber/15 px-1.5 py-0.5 text-action-orange">
                              incorrect → {s.next_on_incorrect}
                            </span>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="sheet overflow-hidden">
                <CardHeader
                  icon={<Link2 className="h-4 w-4" />}
                  title={`Question Links · ${node.children.question_links.length}`}
                />
                <ul>
                  {node.children.question_links.map((q) => (
                    <li key={`${q.question_id}-${q.micro_skill_id}`} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                      <p className="text-sm text-ink">{q.question_text}</p>
                      <div className="mt-1 flex flex-wrap gap-2 text-2xs text-slate-blue">
                        <span className="font-mono">{q.question_id}</span>
                        <span>{q.micro_skill_name}</span>
                        <span>priority {q.priority}</span>
                      </div>
                    </li>
                  ))}
                  {node.children.question_links.length === 0 && (
                    <li className="px-5 py-6 text-center text-sm text-slate-blue">Not attached to any question.</li>
                  )}
                </ul>
              </section>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <section key={g.misconception_id} className="sheet overflow-hidden">
              <CardHeader icon={<Copy className="h-4 w-4" />} title={`${g.label} · ${g.items.length}`} />
              <ul>
                {g.items.map((item, i) => (
                  <li key={i} className="flex items-center gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
                    <span className="min-w-0 flex-1 text-sm text-ink">{String(item.label ?? '—')}</span>
                    <span className="font-mono text-2xs text-slate-blue">{String(item.parallel_example_id ?? '')}</span>
                  </li>
                ))}
                {g.items.length === 0 && (
                  <li className="px-5 py-6 text-center text-sm text-slate-blue">No parallel examples.</li>
                )}
              </ul>
            </section>
          ))}
          {groups.length === 0 && (
            <div className="sheet px-5 py-8 text-center text-sm text-slate-blue">No parallel examples in this topic.</div>
          )}
        </div>
      )}
    </div>
  );
}
