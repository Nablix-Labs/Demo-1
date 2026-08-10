'use client';

/**
 * Misconceptions — v3 page 11. Selecting a misconception replaces every child
 * list with that misconception's own mappings. Affected questions are derived
 * impact, not editable children (guide §9.1).
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, Plus, Lightbulb, Image as ImageIcon, Target, Copy, HelpCircle } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { MisconceptionsData, SupportChild } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

function SupportList({
  icon,
  title,
  items,
  addLabel,
}: {
  icon: React.ReactNode;
  title: string;
  items: SupportChild[];
  addLabel: string;
}) {
  return (
    <section className="sheet overflow-hidden">
      <CardHeader icon={icon} title={`${title} · ${items.length}`} />
      {items.length === 0 ? (
        <div className="px-5 py-6 text-center">
          <p className="text-sm font-semibold text-action-orange">None created for this misconception.</p>
          <button className="btn btn-secondary mt-2">
            <Plus className="h-4 w-4" /> {addLabel}
          </button>
        </div>
      ) : (
        <ol>
          {items.map((c) => (
            <li
              key={c.hint_id ?? c.visual_cue_id}
              className="flex items-center gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                {c.sequence_order}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-ink">{c.preview || c.label}</span>
              </span>
              {(c.shared_by_misconception_count ?? 0) > 1 && (
                <span className="rounded-md bg-learning-blue/12 px-1.5 py-0.5 text-2xs font-bold text-learning-blue">
                  shared ×{c.shared_by_misconception_count}
                </span>
              )}
              <HealthBadge health={c.content_health} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default function MisconceptionsPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<MisconceptionsData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getMisconceptions(topicId).then((d) => {
      setData(d);
      setSelected(d.default_selection.misconception_id);
    });
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const nodes = data.hierarchy.misconceptions;
  const node = nodes.find((m) => m.misconception_id === selected) ?? null;
  const detail = data.selected_item.details.misconception_id === selected ? data.selected_item : null;
  const children = detail?.children ?? node?.children;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Misconceptions"
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
        title="Errors & Misconceptions"
        description="What students get wrong, the errors that diagnose it, and the support that repairs it."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Misconception
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <section className="sheet overflow-hidden self-start">
          <CardHeader icon={<AlertTriangle className="h-4 w-4" />} title={`Misconceptions · ${nodes.length}`} />
          <ul>
            {nodes.map((m) => {
              const active = m.misconception_id === selected;
              return (
                <li key={m.misconception_id}>
                  <button
                    onClick={() => setSelected(m.misconception_id)}
                    className={cn(
                      'flex w-full items-start gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                      active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className={cn('block text-sm font-semibold', active ? 'text-white' : 'text-focus-navy')}>
                        {m.label}
                      </span>
                      <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                        {m.child_counts.hints ?? 0} hints · {m.child_counts.visual_cues ?? 0} cues ·{' '}
                        {m.child_counts.linked_errors ?? 0} errors
                      </span>
                    </span>
                    <HealthBadge health={m.content_health} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="min-w-0 space-y-4">
          {node && <HealthIssues health={node.content_health} />}

          {detail && (
            <section className="sheet overflow-hidden">
              <CardHeader icon={<AlertTriangle className="h-4 w-4" />} title={detail.details.name} />
              <div className="px-5 py-4">
                <p className="text-sm text-ink">{detail.details.description}</p>
                <div className="mt-2 grid gap-x-6 sm:grid-cols-2">
                  {detail.details.diagnosis_rule && <Meta label="Diagnosis" value={detail.details.diagnosis_rule} />}
                  <Meta label="Active" value={detail.details.active ? 'Yes' : 'No'} />
                  <Meta label="Version" value={detail.details.version} />
                </div>
              </div>
            </section>
          )}

          {children && (
            <>
              <section className="sheet overflow-hidden">
                <CardHeader icon={<Target className="h-4 w-4" />} title="Linked Errors & Micro-skills" />
                <div className="space-y-2 px-5 py-4">
                  <ul className="space-y-1.5">
                    {children.linked_errors.map((e) => (
                      <li key={e.error_code} className="flex items-center gap-2 text-sm">
                        <span className="font-mono text-2xs font-bold text-focus-navy">{e.error_code}</span>
                        <span className="text-ink">{e.label}</span>
                        <span className="ml-auto font-mono text-2xs text-slate-blue">w {e.confidence_weight}</span>
                      </li>
                    ))}
                    {children.linked_errors.length === 0 && (
                      <li className="text-sm font-semibold text-danger">No linked error — this blocks review.</li>
                    )}
                  </ul>
                  <ul className="space-y-1.5 border-t border-muted-gray/50 pt-2">
                    {children.linked_micro_skills.map((s) => (
                      <li key={s.micro_skill_id} className="flex items-center gap-2 text-sm">
                        <span className="font-mono text-2xs text-slate-blue">{s.micro_skill_id}</span>
                        <span className="text-ink">{s.label}</span>
                        <span className="ml-auto text-2xs text-slate-blue">{s.relationship_type}</span>
                      </li>
                    ))}
                    {children.linked_micro_skills.length === 0 && (
                      <li className="text-sm font-semibold text-danger">No linked micro-skill — this blocks review.</li>
                    )}
                  </ul>
                </div>
              </section>

              <SupportList icon={<Lightbulb className="h-4 w-4" />} title="Hints" items={children.hints} addLabel="Add Hint" />
              <SupportList
                icon={<ImageIcon className="h-4 w-4" />}
                title="Visual Cues"
                items={children.visual_cues}
                addLabel="Add Visual Cue"
              />

              <section className="sheet overflow-hidden">
                <CardHeader
                  icon={<Copy className="h-4 w-4" />}
                  title={`Parallel Examples · ${children.parallel_examples.length}`}
                />
                <ul>
                  {children.parallel_examples.map((p) => (
                    <li
                      key={p.parallel_example_id}
                      className="flex items-center gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0"
                    >
                      <span className="min-w-0 flex-1 truncate text-sm text-ink">{p.label}</span>
                      <HealthBadge health={p.content_health} />
                    </li>
                  ))}
                  {children.parallel_examples.length === 0 && (
                    <li className="px-5 py-6 text-center text-sm text-slate-blue">No parallel examples.</li>
                  )}
                </ul>
              </section>
            </>
          )}

          {detail && (
            <section className="sheet overflow-hidden">
              <CardHeader
                icon={<HelpCircle className="h-4 w-4" />}
                title={`Affected Questions · ${detail.affected_questions.length}`}
                action={<span className="text-2xs text-slate-blue">derived impact — edit on the question page</span>}
              />
              <ul>
                {detail.affected_questions.map((q) => (
                  <li key={q.question_id} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                    <p className="text-sm text-ink">{q.question_text}</p>
                    <div className="mt-1 flex flex-wrap gap-2 text-2xs text-slate-blue">
                      <span className="font-mono">{q.question_id}</span>
                      <span>{q.phase}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
