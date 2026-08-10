'use client';

import { useState } from 'react';
import { HelpCircle, Plus, Target } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { SectionHeader, SectionLoading, WeightChip } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { QuestionWizard } from '@/components/nablix/QuestionWizard';
import type { Phase, Question } from '@/lib/api/contracts';
import { cn } from '@/lib/utils';

const PHASES: { id: Phase; label: string; tone: string }[] = [
  { id: 'PHASE_0_DIAGNOSTIC', label: 'Phase 0 · Diagnostic', tone: 'text-learning-blue' },
  { id: 'PHASE_2_GUIDED_LEARNING', label: 'Phase 2 · Guided Learning', tone: 'text-dark-cyan' },
  { id: 'PHASE_3_INDEPENDENT_PRACTICE', label: 'Phase 3 · Independent Practice', tone: 'text-action-orange' },
];

function QuestionCard({ q }: { q: Question }) {
  return (
    <div className="rounded-lg border border-muted-gray/70 bg-white p-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-ink">{q.question_text}</p>
        <StatusPill status={q.status} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs text-slate-blue">
        <span className="font-mono">{q.question_id}</span>
        <span className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">{q.question_type}</span>
        <span className="rounded bg-reading-surface px-1.5 py-0.5 font-semibold ring-1 ring-inset ring-muted-gray/70">Difficulty {q.difficulty}</span>
        <span className="font-mono text-slate-blue/80">{q.item_family_id}</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-muted-gray/50 pt-2">
        <span className="flex items-center gap-1 text-2xs font-semibold text-slate-blue">
          <Target className="h-3 w-3" /> {q.question_role}
        </span>
        {q.skill_mappings.map((m) => (
          <span key={m.micro_skill_id} className="flex items-center gap-1.5">
            <span className="font-mono text-2xs text-slate-blue/80">{m.micro_skill_id.split('.').pop()}</span>
            <WeightChip weight={m.weight} primary={m.is_primary} />
          </span>
        ))}
      </div>
    </div>
  );
}

export default function QuestionsPage() {
  const c = useContent();
  const [creating, setCreating] = useState(false);
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Questions"
        icon={<HelpCircle className="h-3.5 w-3.5" />}
        title="Question Builder"
        description="Question, usage, micro-skill mapping and answer specification are authored together in one guided flow."
        action={
          !creating && (
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> New Question
            </button>
          )
        }
      />

      {creating && <QuestionWizard microSkills={c.micro_skills} onClose={() => setCreating(false)} />}

      {PHASES.map((p) => {
        const qs = c.questions.filter((q) => q.phase === p.id);
        return (
          <section key={p.id}>
            <div className="mb-2 flex items-center gap-2">
              <h2 className={cn('font-display text-sm font-bold', p.tone)}>{p.label}</h2>
              <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold tabular-nums text-slate-blue ring-1 ring-inset ring-muted-gray/70">
                {qs.length}
              </span>
            </div>
            <div className="grid gap-2">
              {qs.length ? qs.map((q) => <QuestionCard key={q.question_id} q={q} />) : (
                <div className="rounded-lg border border-dashed border-muted-gray bg-white/50 px-3 py-4 text-center text-xs text-slate-blue">
                  No questions in this phase yet.
                </div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
