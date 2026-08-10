'use client';

import { useState } from 'react';
import { Check, ChevronLeft, ChevronRight, ShieldCheck, X } from 'lucide-react';
import type { MicroSkillDetail, Phase, QuestionType } from '@/lib/api/contracts';
import { cn } from '@/lib/utils';

const STEPS = ['Question', 'Phase & Usage', 'Micro-skills', 'Answer', 'Errors'];

const TYPES: { value: QuestionType; label: string }[] = [
  { value: 'SINGLE_CHOICE', label: 'Single choice' },
  { value: 'SHORT_RESPONSE', label: 'Short response' },
  { value: 'MULTI_PART_SHORT_RESPONSE', label: 'Multi-part' },
  { value: 'CHOICE_WITH_EXPLANATION', label: 'Choice + explanation' },
  { value: 'TRUE_FALSE_WITH_EXPLANATION', label: 'True/false + explanation' },
];

// Phase-dependent defaults — spec §10.7. Selecting a phase locks role/support/attempts.
const PHASE_DEFAULTS: Record<Phase, { label: string; role: string; attempts: number; support: string }> = {
  PHASE_0_DIAGNOSTIC: { label: 'Phase 0 · Diagnostic', role: 'DIAGNOSTIC', attempts: 1, support: 'NO_SUPPORT_DURING_ATTEMPT' },
  PHASE_2_GUIDED_LEARNING: { label: 'Phase 2 · Guided Learning', role: 'CLOSE_PRACTICE', attempts: 2, support: 'ADAPTIVE_SUPPORT' },
  PHASE_3_INDEPENDENT_PRACTICE: { label: 'Phase 3 · Independent Practice', role: 'INDEPENDENT_VERIFICATION', attempts: 1, support: 'NO_SUPPORT_DURING_ATTEMPT' },
};

export function QuestionWizard({
  microSkills,
  onClose,
}: {
  /** Only the identity fields are needed, so either contract's skill type fits. */
  microSkills: Pick<MicroSkillDetail, 'micro_skill_id' | 'skill_code' | 'skill_name'>[];
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [type, setType] = useState<QuestionType>('SINGLE_CHOICE');
  const [difficulty, setDifficulty] = useState<1 | 2>(1);
  const [phase, setPhase] = useState<Phase>('PHASE_0_DIAGNOSTIC');
  const [skills, setSkills] = useState<Record<string, { primary: boolean }>>({});
  const d = PHASE_DEFAULTS[phase];

  const toggleSkill = (id: string) =>
    setSkills((s) => {
      const next = { ...s };
      if (next[id]) delete next[id];
      else next[id] = { primary: Object.keys(s).length === 0 };
      return next;
    });

  return (
    <section className="sheet lg-anim-rise overflow-hidden">
      {/* Stepper */}
      <div className="flex items-center gap-1 border-b border-muted-gray/70 px-4 py-3">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center">
            <button
              onClick={() => setStep(i)}
              className={cn(
                'flex items-center gap-2 rounded-pill px-2.5 py-1 text-xs font-semibold transition-colors',
                i === step ? 'bg-focus-navy text-white' : i < step ? 'text-learning-blue' : 'text-slate-blue',
              )}
            >
              <span
                className={cn(
                  'flex h-5 w-5 items-center justify-center rounded-full text-2xs font-bold',
                  i === step ? 'bg-white text-focus-navy' : i < step ? 'bg-learning-blue text-white' : 'bg-muted-gray text-slate-blue',
                )}
              >
                {i < step ? <Check className="h-3 w-3" strokeWidth={3} /> : i + 1}
              </span>
              <span className="hidden sm:inline">{s}</span>
            </button>
            {i < STEPS.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-muted-gray" />}
          </div>
        ))}
        <button onClick={onClose} className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg text-slate-blue hover:bg-reading-surface">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-5">
        {step === 0 && (
          <div className="space-y-4">
            <div>
              <label className="label">Question text</label>
              <textarea className="field min-h-[80px]" placeholder="The exact student-facing question…" defaultValue="A rule adds 5 to any number n. Write the rule, then find the result when n = 9." />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Question type</label>
                <div className="flex flex-wrap gap-1.5">
                  {TYPES.map((t) => (
                    <button
                      key={t.value}
                      onClick={() => setType(t.value)}
                      className={cn(
                        'rounded-pill px-2.5 py-1 text-2xs font-semibold ring-1 ring-inset transition-colors',
                        type === t.value ? 'bg-learning-blue text-white ring-learning-blue' : 'bg-reading-surface text-slate-blue ring-muted-gray/70',
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="label">Difficulty</label>
                <div className="inline-flex overflow-hidden rounded-btn ring-1 ring-inset ring-muted-gray/70">
                  {([1, 2] as const).map((n) => (
                    <button
                      key={n}
                      onClick={() => setDifficulty(n)}
                      className={cn('px-4 py-1.5 text-sm font-semibold', difficulty === n ? 'bg-focus-navy text-white' : 'bg-white text-slate-blue')}
                    >
                      {n === 1 ? '1 · Foundational' : '2 · Standard'}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="label">Item family</label>
                <input className="field font-mono" defaultValue="FAM-T02-ENCODE-ADD-CONSTANT" />
              </div>
              <div>
                <label className="label">Source</label>
                <input className="field" defaultValue="Nablix KS3 Algebra Foundations Pack" />
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="label">Phase</label>
              <div className="grid gap-2 sm:grid-cols-3">
                {(Object.keys(PHASE_DEFAULTS) as Phase[]).map((p) => (
                  <button
                    key={p}
                    onClick={() => setPhase(p)}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-left text-sm font-semibold transition-colors',
                      phase === p ? 'border-learning-blue bg-learning-blue/8 text-learning-blue' : 'border-muted-gray/70 bg-white text-slate-blue',
                    )}
                  >
                    {PHASE_DEFAULTS[p].label}
                  </button>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-learning-blue/25 bg-learning-blue/8 p-3">
              <div className="text-2xs font-bold uppercase tracking-wide text-learning-blue">Applied automatically from phase</div>
              <div className="mt-2 grid grid-cols-3 gap-3 font-mono text-xs text-focus-navy">
                <div>
                  <div className="text-2xs font-sans font-semibold text-slate-blue">Role</div>
                  {d.role}
                </div>
                <div>
                  <div className="text-2xs font-sans font-semibold text-slate-blue">Attempts</div>
                  {d.attempts}
                </div>
                <div>
                  <div className="text-2xs font-sans font-semibold text-slate-blue">Support</div>
                  {d.support}
                </div>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-2">
            <label className="label">Map micro-skills · mark at least one primary</label>
            {microSkills.map((m) => {
              const sel = skills[m.micro_skill_id];
              return (
                <div key={m.micro_skill_id} className={cn('flex items-center gap-3 rounded-lg border px-3 py-2', sel ? 'border-learning-blue/40 bg-learning-blue/6' : 'border-muted-gray/70 bg-white')}>
                  <button
                    onClick={() => toggleSkill(m.micro_skill_id)}
                    className={cn('flex h-5 w-5 items-center justify-center rounded-md ring-1 ring-inset', sel ? 'bg-learning-blue text-white ring-learning-blue' : 'bg-white ring-muted-gray')}
                  >
                    {sel && <Check className="h-3.5 w-3.5" strokeWidth={3} />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-2xs font-bold text-focus-navy">{m.skill_code}</span>
                    <span className="ml-2 text-sm text-ink">{m.skill_name}</span>
                  </div>
                  {sel && (
                    <button
                      onClick={() => setSkills((s) => ({ ...s, [m.micro_skill_id]: { primary: !s[m.micro_skill_id].primary } }))}
                      className={cn('rounded-md px-2 py-0.5 text-2xs font-bold', sel.primary ? 'bg-learning-blue/12 text-learning-blue' : 'text-slate-blue hover:bg-reading-surface')}
                    >
                      {sel.primary ? 'primary' : 'mark primary'}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div>
              <label className="label">Canonical answer</label>
              <input className="field font-mono" defaultValue="n + 5; 14" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Verification method</label>
                <input className="field font-mono text-xs" defaultValue="STRUCTURED_TEXT_AND_SYMBOLIC_MATCH" />
              </div>
              <div>
                <label className="label">Accepted answers</label>
                <input className="field" placeholder="add 5 to n | n plus 5" />
              </div>
            </div>
            {type === 'SINGLE_CHOICE' && (
              <div className="rounded-lg bg-reading-surface p-3 text-xs text-slate-blue">
                Single-choice selected — an option builder with correct option and distractors is shown here.
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3">
            <label className="label">Known wrong response → error mapping (optional)</label>
            <div className="grid gap-2 sm:grid-cols-2">
              <input className="field font-mono" placeholder="response pattern (e.g. “5”)" />
              <input className="field font-mono" placeholder="error code (e.g. ERR-DROP-LETTER)" />
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-highlight-amber/10 px-3 py-2 text-xs text-action-orange">
              For multi-skill questions, identify which mapped skill the error affects (spec §10.11).
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-muted-gray/70 px-5 py-3">
        <button className="btn btn-ghost" onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>
          <ChevronLeft className="h-4 w-4" /> Back
        </button>
        <div className="flex items-center gap-2">
          <button className="btn btn-secondary">
            <ShieldCheck className="h-4 w-4" /> Validate
          </button>
          {step < STEPS.length - 1 ? (
            <button className="btn btn-primary" onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}>
              Next <ChevronRight className="h-4 w-4" />
            </button>
          ) : (
            <button className="btn btn-primary" onClick={onClose}>
              Save Draft
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
