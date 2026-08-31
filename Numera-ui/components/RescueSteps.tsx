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
import { findReturnSurfaces, returnToQuestion } from '@/lib/rescueReturn';
import StickyNote from '@/components/StickyNote';

const TITLE = {
  PARALLEL: 'A similar one',
  TUTOR_SOLVED: 'Let me show you',
} as const;

export default function RescueSteps() {
  const steps = useNumeraStore((s) => s.rescueSteps);
  const clearRescueSteps = useNumeraStore((s) => s.clearRescueSteps);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const sessionId = useNumeraStore((s) => s.sessionId);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);

  // Whether an advance is outstanding, and for WHICH rescue.
  //
  // The rescue id has to be part of it. This component never unmounts —
  // SupportLane renders it unconditionally — so a bare step number survived
  // into the next rescue: press Next on step 3 of rescue A, A is superseded by
  // B starting at step 1, and B opened with its button already disabled and no
  // way to re-enable it.
  const [awaiting, setAwaiting] = useState<{ rescueId: string; step: number } | null>(null);
  /**
   * Set when a press could not be delivered at all.
   *
   * Rescue events ride the voice socket (hooks/useWebSocket registers the only
   * transport). A student in text mode, or one whose socket has dropped, has
   * nothing carrying the advance — and the button then did LITERALLY nothing:
   * no step, no latch, no message. Verified in the browser on 31 Aug with the
   * presentation flag on and the socket closed.
   *
   * The component's own contract is that a press which goes nowhere must say
   * what it is waiting for rather than pretend; that only held for a press that
   * was actually sent. This is the other half.
   *
   * Keyed to the step it happened on, for the same reason `awaiting` is keyed
   * to the rescue: held as a bare boolean it survived onto the steps that DID
   * arrive, so step 2 rendered with "couldn't ask for the next step" sitting
   * under it — a failure notice attached to a success.
   */
  const [undeliverable, setUndeliverable] =
    useState<{ rescueId: string; step: number } | null>(null);

  if (steps.length === 0) return null;
  // Phase 3 is answered alone (spec §3.2). Support does not appear during an
  // independent attempt — the same rule the store enforces on the actions.
  if (isPhase3(currentPhase)) return null;

  const current = steps[steps.length - 1];
  const final = isFinalStep(current);
  // Outstanding only for this rescue, and only until the step it asked for
  // arrives. Anything else — a new rescue, a step that went backwards — clears
  // it rather than leaving the student holding a dead button.
  const pending = awaiting !== null
    && awaiting.rescueId === current.rescueId
    && awaiting.step > current.stepIndex;
  /** Only for the step the student actually pressed on. */
  const failedToSend = undeliverable !== null
    && undeliverable.rescueId === current.rescueId
    && undeliverable.step === current.stepIndex;

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
    // Only latch on a send that actually left. A closed socket, or a backend
    // that does not know this frame yet, must not leave the button reading
    // "Waiting for the next step…" for the rest of the question.
    setUndeliverable(
      sent ? null : { rescueId: current.rescueId, step: current.stepIndex },
    );
    if (sent) setAwaiting({ rescueId: current.rescueId, step: current.stepIndex + 1 });
  };

  const onReturn = () => {
    // Dismisses the presentation. The question, the canvas and the student's
    // own working are all still underneath it, untouched — nothing here erases
    // or replaces student work, which the handoff states twice.
    clearRescueSteps();
    setAwaiting(null);
    setUndeliverable(null);
    // ...and puts the student back where they answer (Sanya's item 3, "return
    // focus to the original problem and restore normal input"). This used to
    // be a console.log, so the panel vanished and the student was left with
    // the caret nowhere after several steps of reading.
    //
    // The backend's `return_target_object_id` is deliberately NOT read here:
    // it names a question token, and nothing on the canvas can focus a single
    // token, so acting on it would be the same silent no-op in a new place. It
    // stays on the step (RescueStep.returnTargetObjectId) for whenever a real
    // focus mechanism exists. See lib/rescueReturn.
    returnToQuestion(findReturnSurfaces(document));
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
          {current.totalSteps === null
            ? `Step ${current.stepIndex}`
            : `Step ${current.stepIndex} of ${current.totalSteps}`}
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
          {failedToSend && !pending && (
            <span role="status" className="text-xs text-slate-500">
              Couldn&apos;t ask for the next step — try again in a moment.
            </span>
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
