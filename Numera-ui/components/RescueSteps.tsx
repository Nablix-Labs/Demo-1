'use client';

/**
 * RescueSteps — the step-at-a-time rescue presentation (handoff, 22 Aug 2026).
 *
 * Shows the authored steps that have actually arrived, and offers the two
 * controls the handoff asks for: "Next step" while there are more, and "Return
 * to original" on the last one.
 *
 * What it deliberately does NOT do is advance anything. "Next step" sends
 * RESCUE_STEP_ADVANCE and then waits — the step list grows when the backend
 * sends the next step, not when the button is pressed. That is the whole point
 * of the inverted contract: a client that advanced its own view would be
 * showing the student a position the backend does not agree they are at, and
 * the first time the two disagreed it would be about how much of a worked
 * solution the student had earned.
 *
 * So a press that goes nowhere shows nothing new. That reads as unresponsive,
 * which is why the button reports what it is waiting for rather than pretending
 * to have worked.
 *
 * This is the panel half. TUTOR_SOLVED steps are also written onto the tutor
 * layer by `actionMarks` — the handoff asks for them there specifically — and
 * both are fed from the same `rescueSteps`, so they cannot disagree.
 */

import { useState } from 'react';
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import { isFinalStep } from '@/lib/rescueActions';
import { emitRescueAdvance } from '@/lib/rescueEvents';
import StickyNote from '@/components/StickyNote';

const TITLE = {
  PARALLEL: 'A similar one',
  TUTOR_SOLVED: 'Let me show you',
} as const;

export default function RescueSteps() {
  const steps = useNumeraStore((s) => s.rescueSteps);
  const returnTarget = useNumeraStore((s) => s.rescueReturnTarget);
  const clearRescueSteps = useNumeraStore((s) => s.clearRescueSteps);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const sessionId = useNumeraStore((s) => s.sessionId);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);

  // Whether an advance is outstanding. Local, because it is about this
  // button's last press and nothing else in the app has an opinion on it.
  const [awaitingStep, setAwaitingStep] = useState<number | null>(null);

  if (steps.length === 0) return null;
  // Phase 3 is answered alone (spec §3.2). Support does not appear during an
  // independent attempt — the same rule the store enforces on the actions.
  if (isPhase3(currentPhase)) return null;

  const current = steps[steps.length - 1];
  const final = isFinalStep(current);
  // A press is only outstanding until the step it asked for arrives.
  const pending = awaitingStep !== null && awaitingStep > current.stepIndex;

  const onNext = () => {
    if (!sessionId || !activeQuestionId) return;
    const sent = emitRescueAdvance({
      event_type: 'RESCUE_STEP_ADVANCE',
      session_id: sessionId,
      question_id: activeQuestionId,
      rescue_id: current.rescueId,
      // The step being LOOKED AT, never pre-incremented: Chirudeva rejects the
      // request unless it matches the persisted index, which is what makes a
      // double-press a no-op rather than a skipped step.
      current_step_index: current.stepIndex,
      trigger: 'UI_NEXT_STEP',
    });
    if (sent) setAwaitingStep(current.stepIndex + 1);
  };

  const onReturn = () => {
    // Dismisses the presentation. The question, the canvas and the student's
    // own working are all still underneath it, untouched — nothing here erases
    // or replaces student work, which the handoff states twice.
    clearRescueSteps();
    if (returnTarget) {
      // Focus is the backend's stated return target. We record the intent; the
      // canvas owns where that id actually is.
      console.log('[rescue] returning to', returnTarget);
    }
  };

  return (
    <aside className="relative max-w-[22rem]" aria-label={TITLE[current.mode]}>
      <StickyNote tone="sky" label={TITLE[current.mode]}>

        <ol className="mt-2 space-y-2">
          {steps.map((step) => (
            <li
              key={step.actionId}
              className={
                step.answerReveal
                  ? 'text-[15px] font-semibold leading-snug text-slate-900'
                  : 'text-[15px] leading-snug text-slate-700'
              }
            >
              {step.text}
            </li>
          ))}
        </ol>

        <p className="mt-2 text-xs text-slate-500">
          Step {current.stepIndex} of {current.totalSteps}
        </p>

        <div className="mt-3 flex items-center gap-2">
          {!final && (
            <button
              type="button"
              onClick={onNext}
              disabled={pending}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm
                         font-medium text-slate-700 hover:bg-slate-200/60
                         disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending ? 'Waiting for the next step…' : 'Next step'}
              {!pending && <ChevronRight className="h-4 w-4" aria-hidden />}
            </button>
          )}
          {final && (
            <button
              type="button"
              onClick={onReturn}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm
                         font-medium text-slate-700 hover:bg-slate-200/60"
            >
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Return to original
            </button>
          )}
        </div>
      </StickyNote>
    </aside>
  );
}
