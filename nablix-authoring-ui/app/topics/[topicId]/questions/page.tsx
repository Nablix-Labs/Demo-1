'use client';

/**
 * Questions — v3 pages 08/09/10. One shape, three phases; the phase decides
 * which questions are listed and which usage rules apply.
 *
 * Selecting a question replaces the whole package — usage, skill mappings,
 * answer specification and error mappings change together. Nothing from the
 * previously selected question stays on screen (guide §8).
 */
import { useEffect, useState } from 'react';
import { HelpCircle, Plus, Target, ListChecks, CheckCircle2, AlertOctagon } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, WeightChip, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { QuestionWizard } from '@/components/nablix/QuestionWizard';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { MicroSkill, QuestionPhase, QuestionsData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

const PHASES: { id: QuestionPhase; label: string }[] = [
  { id: 'PHASE_0_DIAGNOSTIC', label: 'Phase 0 · Diagnostic' },
  { id: 'PHASE_2_GUIDED_LEARNING', label: 'Phase 2 · Guided' },
  { id: 'PHASE_3_INDEPENDENT_PRACTICE', label: 'Phase 3 · Independent' },
];

export default function QuestionsPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [phase, setPhase] = useState<QuestionPhase>('PHASE_0_DIAGNOSTIC');
  const [data, setData] = useState<QuestionsData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [skills, setSkills] = useState<MicroSkill[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let live = true;
    setData(null);
    apiV3.getQuestions(topicId, phase).then((d) => {
      if (!live) return;
      setData(d);
      setSelected(d.default_selection.question_id);
    });
    return () => {
      live = false;
    };
  }, [topicId, phase]);

  useEffect(() => {
    apiV3.getMicroSkills(topicId).then((d) => setSkills([d.selected_item.details]));
  }, [topicId]);

  const questions = data?.hierarchy.questions ?? [];
  const node = questions.find((q) => q.question_id === selected) ?? null;
  /** The package the API sent is only valid for the question it was built for. */
  const pkg = data && data.selected_item.question.question_id === selected ? data.selected_item : null;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Questions"
        icon={<HelpCircle className="h-3.5 w-3.5" />}
        title="Question Builder"
        description="Question, usage, micro-skill mapping, answer specification and error mappings form one package."
        action={
          !creating && (
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> New Question
            </button>
          )
        }
      />

      {creating && <QuestionWizard microSkills={skills} onClose={() => setCreating(false)} />}

      <div className="flex flex-wrap items-center gap-1 border-b border-muted-gray/70">
        {PHASES.map((p) => (
          <button
            key={p.id}
            onClick={() => setPhase(p.id)}
            className={cn(
              'rounded-t-lg px-3 py-2 text-sm font-semibold',
              phase === p.id
                ? 'bg-white text-focus-navy shadow-[inset_0_-2px_0_0_var(--lime)]'
                : 'text-slate-blue hover:text-ink',
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {!data ? (
        <SectionLoading />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
          <section className="sheet overflow-hidden self-start">
            <CardHeader icon={<ListChecks className="h-4 w-4" />} title={`${data.phase.label} · ${questions.length}`} />
            {questions.length === 0 ? (
              <div className="px-5 py-8 text-center text-sm text-slate-blue">No questions in this phase yet.</div>
            ) : (
              <ol>
                {questions.map((q) => {
                  const active = q.question_id === selected;
                  return (
                    <li key={q.question_id}>
                      <button
                        onClick={() => setSelected(q.question_id)}
                        className={cn(
                          'flex w-full items-start gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                          active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                        )}
                      >
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/15 font-mono text-2xs font-bold">
                          <span className={active ? 'text-white' : 'text-focus-navy'}>{q.sequence_order}</span>
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={cn('block truncate text-sm', active ? 'text-white' : 'text-ink')}>{q.label}</span>
                          <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                            {q.question_type} · difficulty {q.difficulty}
                          </span>
                        </span>
                        <HealthBadge health={q.content_health} />
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          <div className="min-w-0 space-y-4">
            {node && <HealthIssues health={node.content_health} />}

            {pkg && (
              <>
                <section className="sheet overflow-hidden">
                  <CardHeader icon={<HelpCircle className="h-4 w-4" />} title="Question" />
                  <div className="space-y-2 px-5 py-4">
                    <p className="text-sm text-ink">{pkg.question.question_text}</p>
                    <div className="grid gap-x-6 sm:grid-cols-2">
                      <Meta label="ID" value={<span className="font-mono text-xs">{pkg.question.question_id}</span>} />
                      <Meta label="Type" value={pkg.question.question_type} />
                      <Meta label="Difficulty" value={pkg.question.difficulty} />
                      <Meta label="Item family" value={<span className="font-mono text-xs">{pkg.question.item_family_id}</span>} />
                      <Meta label="Version" value={pkg.question.version} />
                      <Meta label="Status" value={pkg.question.status} />
                    </div>
                  </div>
                </section>

                <section className="sheet overflow-hidden">
                  <CardHeader icon={<Target className="h-4 w-4" />} title="Usage & Micro-skills" />
                  <div className="space-y-2 px-5 py-4">
                    {pkg.children.usage ? (
                      <div className="grid gap-x-6 sm:grid-cols-2">
                        <Meta label="Phase" value={pkg.children.usage.phase} />
                        <Meta label="Role" value={pkg.children.usage.question_role} />
                        <Meta label="Support" value={pkg.children.usage.support_allowed} />
                        <Meta label="Max attempts" value={pkg.children.usage.max_attempts} />
                      </div>
                    ) : (
                      <p className="text-sm font-semibold text-danger">Question Usage is missing — this blocks review.</p>
                    )}
                    <div className="flex flex-wrap items-center gap-2 border-t border-muted-gray/50 pt-2">
                      {pkg.children.micro_skill_mappings.length ? (
                        pkg.children.micro_skill_mappings.map((m) => (
                          <span key={m.micro_skill_id} className="flex items-center gap-1.5">
                            <span className="font-mono text-2xs text-slate-blue/80">{m.micro_skill_id}</span>
                            <WeightChip weight={m.weight} primary={m.is_primary} />
                          </span>
                        ))
                      ) : (
                        <span className="text-sm font-semibold text-danger">No micro-skill mapping — this blocks review.</span>
                      )}
                    </div>
                  </div>
                </section>

                <section className="sheet overflow-hidden">
                  <CardHeader icon={<CheckCircle2 className="h-4 w-4" />} title="Answer Specification" />
                  <div className="px-5 py-4">
                    {pkg.children.answer_specification ? (
                      <div className="grid gap-x-6 sm:grid-cols-2">
                        <Meta label="Canonical" value={pkg.children.answer_specification.canonical_answer} />
                        <Meta label="Answer type" value={pkg.children.answer_specification.answer_type} />
                        <Meta label="Accepted" value={pkg.children.answer_specification.accepted_answers.join(' · ') || '—'} />
                        <Meta label="Common wrong" value={pkg.children.answer_specification.common_wrong_answers.join(' · ') || '—'} />
                        <Meta label="Verification" value={pkg.children.answer_specification.verification_method} />
                        <Meta label="Explanation" value={pkg.children.answer_specification.explanation_required ? 'Required' : 'Not required'} />
                        {pkg.children.answer_specification.answer_steps.length > 0 && (
                          <div className="sm:col-span-2">
                            <Meta
                              label="Answer steps"
                              value={
                                <ol className="list-decimal space-y-0.5 pl-4">
                                  {pkg.children.answer_specification.answer_steps.map((s) => (
                                    <li key={s.step_no}>{s.text}</li>
                                  ))}
                                </ol>
                              }
                            />
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm font-semibold text-danger">Answer Specification is missing — this blocks review.</p>
                    )}
                  </div>
                </section>

                <section className="sheet overflow-hidden">
                  <CardHeader
                    icon={<AlertOctagon className="h-4 w-4" />}
                    title={`Error Mappings · ${pkg.children.error_mappings.length}`}
                  />
                  <ul>
                    {pkg.children.error_mappings.map((m, i) => (
                      <li key={i} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-2xs font-bold text-focus-navy">{m.error.error_code}</span>
                          <span className="text-sm text-ink">{m.error.error_name}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-blue">Pattern: {m.response_pattern}</p>
                        {m.micro_skill_id ? (
                          <p className="mt-1 font-mono text-2xs text-slate-blue">{m.micro_skill_id}</p>
                        ) : (
                          <p className="mt-1 text-2xs font-semibold text-action-orange">
                            No affected micro-skill — Question_Error_Map.micro_skill_id is not in the schema yet.
                          </p>
                        )}
                      </li>
                    ))}
                    {pkg.children.error_mappings.length === 0 && (
                      <li className="px-5 py-6 text-center text-sm text-slate-blue">No error mappings.</li>
                    )}
                  </ul>
                </section>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
