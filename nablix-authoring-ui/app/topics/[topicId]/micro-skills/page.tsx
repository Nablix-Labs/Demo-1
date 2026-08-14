'use client';

/**
 * Micro-skills — v3 page 05. Topic → Micro-skill → linked questions and
 * misconceptions. Selecting a skill replaces every linked list with that
 * skill's own content (guide §6.3).
 */
import { useEffect, useState } from 'react';
import { Target, Plus, HelpCircle, Link2 } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { MicroSkillsData } from '@/lib/api/v3-contracts';
import { useSelectionOverride } from '@/lib/use-selection-override';
import { cn } from '@/lib/utils';

export default function MicroSkillsPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const override = useSelectionOverride();
  const [data, setData] = useState<MicroSkillsData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getMicroSkills(topicId).then((d) => {
      setData(d);
      const named = override.select && d.hierarchy.micro_skills.some((n) => n.micro_skill_id === override.select);
      setSelected(named ? override.select! : d.default_selection.micro_skill_id);
    });
  }, [topicId, override.select]);

  if (!data) return <SectionLoading />;

  const skills = data.hierarchy.micro_skills;
  const node = skills.find((s) => s.micro_skill_id === selected) ?? null;
  const detail = data.selected_item.details.micro_skill_id === selected ? data.selected_item : null;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Micro-skills"
        icon={<Target className="h-3.5 w-3.5" />}
        title="Micro-skills"
        description="Every assessable skill in this topic, with the content that covers it."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Micro-skill
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <section className="sheet overflow-hidden self-start">
          <CardHeader icon={<Target className="h-4 w-4" />} title={`Micro-skills · ${skills.length}`} />
          <ul>
            {skills.map((s) => {
              const active = s.micro_skill_id === selected;
              return (
                <li key={s.micro_skill_id}>
                  <button
                    onClick={() => setSelected(s.micro_skill_id)}
                    className={cn(
                      'flex w-full items-start gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                      active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className={cn('block truncate text-sm font-semibold', active ? 'text-white' : 'text-focus-navy')}>
                        {s.label}
                      </span>
                      <span className={cn('mt-0.5 block font-mono text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                        {s.micro_skill_id}
                      </span>
                    </span>
                    <HealthBadge health={s.content_health} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="min-w-0 space-y-4">
          {node && <HealthIssues health={node.content_health} />}

          {node && (
            <section className="sheet overflow-hidden">
              <CardHeader icon={<Target className="h-4 w-4" />} title="Coverage" />
              <div className="flex flex-wrap gap-2 px-5 py-4">
                {Object.entries(node.coverage_counts).map(([k, v]) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-reading-surface px-2.5 py-1.5 text-2xs font-semibold text-slate-blue ring-1 ring-inset ring-muted-gray/70"
                  >
                    {k.replace(/_/g, ' ')}
                    <span className="font-mono font-bold text-focus-navy tabular-nums">{v}</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          {detail && (
            <>
              <section className="sheet overflow-hidden">
                <CardHeader icon={<Target className="h-4 w-4" />} title={detail.details.skill_name} />
                <div className="px-5 py-4">
                  <p className="text-sm text-ink">{detail.details.description}</p>
                  <div className="mt-2 grid gap-x-6 sm:grid-cols-2">
                    <Meta label="Code" value={<span className="font-mono text-xs">{detail.details.skill_code}</span>} />
                    <Meta label="Priority" value={detail.details.assessment_priority} />
                    <Meta label="Status" value={detail.details.status} />
                    <Meta label="Version" value={detail.details.version} />
                  </div>
                </div>
              </section>

              <section className="sheet overflow-hidden">
                <CardHeader
                  icon={<HelpCircle className="h-4 w-4" />}
                  title={`Linked Questions · ${detail.linked_questions.length}`}
                />
                <ul>
                  {detail.linked_questions.map((q) => (
                    <li key={q.question_id} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                      <p className="text-sm text-ink">{q.question_text}</p>
                      <div className="mt-1 flex flex-wrap gap-2 text-2xs text-slate-blue">
                        <span className="font-mono">{q.question_id}</span>
                        <span>{q.phase}</span>
                        <span>{q.question_role}</span>
                      </div>
                    </li>
                  ))}
                  {detail.linked_questions.length === 0 && (
                    <li className="px-5 py-6 text-center text-sm text-slate-blue">No questions cover this skill yet.</li>
                  )}
                </ul>
              </section>

              <section className="sheet overflow-hidden">
                <CardHeader
                  icon={<Link2 className="h-4 w-4" />}
                  title={`Linked Misconceptions · ${detail.linked_misconceptions.length}`}
                />
                <ul>
                  {detail.linked_misconceptions.map((m) => (
                    <li key={m.misconception_id} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                      <p className="text-sm font-semibold text-focus-navy">{m.name}</p>
                      <p className="mt-0.5 text-xs text-slate-blue">{m.description}</p>
                    </li>
                  ))}
                  {detail.linked_misconceptions.length === 0 && (
                    <li className="px-5 py-6 text-center text-sm text-slate-blue">No misconceptions linked.</li>
                  )}
                </ul>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
