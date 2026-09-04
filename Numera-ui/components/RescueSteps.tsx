'use client';

/**
 * RescueSteps — the step-at-a-time rescue presentation (handoff, 22 Aug 2026).
 *
 * Shows the authored step the student is on — one at a time, replaced rather
 * than appended — and offers the two controls the handoff asks for: "Next
 * step" while there are more, and "Return to original" on the last one.
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

import { useEffect, useState } from 'react';
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import { isFinalStep } from '@/lib/rescueActions';
import { advanceFailed, advancePending } from '@/lib/rescueMode';
import { emitRescueAdvance } from '@/lib/rescueEvents';
import { findReturnSurfaces, returnToQuestion } from '@/lib/rescueReturn';
import { nextUnspokenStep, speakRescueStep } from '@/lib/rescueSpeech';
import { tutorSay } from '@/lib/tutorSpeech';
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
  const advanceFailure = useNumeraStore((s) => s.rescueAdvanceFailure);
  const noteAdvanceFailed = useNumeraStore((s) => s.noteRescueAdvanceFailed);
  /** The backend's own word that there are no more steps. */
  const completed = useNumeraStore((s) => s.rescueCompleted);

  // Whether an advance is outstanding, and for WHICH rescue.
  //
  // The rescue id has to be part of it. This component never unmounts —
  // SupportLane renders it unconditionally — so a bare step number survived
  // into the next rescue: press Next on step 3 of rescue A, A is superseded by
  // B starting at step 1, and B opened with its button already disabled and no
  // way to re-enable it.
  const [awaiting, setAwaiting] = useState<{ rescueId: string; step: number } | null>(null);

  /**
   * Say each newly arrived step, once, after its visual.
   *
   * In an effect rather than in the store's reducer because speaking is a side
   * effect on the room, and the reducer must stay a pure state transition — the
   * render acknowledgement next to it takes the same care, deferring into a
   * microtask so a transport failure can never take a render down. Here the
   * reason is stronger still: the effect runs AFTER React has committed the
   * step to the screen, which is the ordering the contract asks for.
   *
   * Deliberately not gated on `pending` or on which control caused the step.
   * The initial parallel example, every tutor-solved step and each Next-step
   * reply all reach the student the same way — as a step appearing in this
   * list — so all three are spoken by this one path, and none of them can be
   * the one that gets forgotten.
   */
  useEffect(() => {
    if (isPhase3(currentPhase)) return;
    const step = nextUnspokenStep(steps);
    if (!step) return;
    speakRescueStep(step, (text) => tutorSay(text, { afterMarks: true }));
  }, [steps, currentPhase]);

  if (steps.length === 0) return null;
  // Phase 3 is answered alone (spec §3.2). Support does not appear during an
  // independent attempt — the same rule the store enforces on the actions.
  if (isPhase3(currentPhase)) return null;

  const current = steps[steps.length - 1];
  // Either the authored count says so, or the backend has told us outright.
  // `total_steps` is nullable, so the count alone left a walkthrough of
  // unstated length with no last step: "Next step" forever and no way back.
  const final = isFinalStep(current) || completed;
  /**
   * Only for the step the student actually pressed on.
   *
   * Held in the store rather than here because the failure is asynchronous —
   * the transport reports success when the POST is FIRED, so a request that
   * left and was then rejected could never reach a latch that only sees the
   * synchronous return. Keyed to the rescue and step for the same reason
   * `awaiting` is: as a bare flag it survived onto the steps that did arrive,
   * putting "couldn't ask for the next step" under a step that had just
   * successfully appeared.
   */
  const failedToSend = advanceFailed(advanceFailure, current);
  // Outstanding only for this rescue, and only until the step it asked for
  // arrives. Anything else — a new rescue, a step that went backwards — clears
  // it rather than leaving the student holding a dead button.
  // Cancelled by a recorded failure. Verified in the browser on 4 Sep against
  // the deployed build: the advance 409'd, the catch recorded the failure, and
  // the button still read "Waiting for the next step…" and stayed disabled —
  // the exact symptom the failure reporting was added to remove. Recording a
  // failure has to RELEASE the latch, not merely sit beside it.
  const pending = advancePending(awaiting, current) && !failedToSend;

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
    // "Waiting for the next step…" for the rest of the question. The other
    // half — a request that left and was rejected — arrives later, through the
    // transport, as `rescueAdvanceFailure`.
    if (sent) {
      // A fresh attempt clears the last one's failure, or the notice would sit
      // under a press that is currently in flight and the latch it releases
      // would leave the button live while a request is outstanding.
      noteAdvanceFailed(null);
      setAwaiting({ rescueId: current.rescueId, step: current.stepIndex + 1 });
    } else {
      noteAdvanceFailed({ rescueId: current.rescueId, step: current.stepIndex });
    }
  };

  const onReturn = () => {
    // Dismisses the presentation. The question, the canvas and the student's
    // own working are all still underneath it, untouched — nothing here erases
    // or replaces student work, which the handoff states twice.
    clearRescueSteps();
    setAwaiting(null);
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

        {/* One step, replaced outright when the next one arrives.
            
            The panel used to accumulate: every step so far stacked in a list
            that grew with each press. That contradicts the contract — Next
            "replaces the current rescue action atomically" — and it grew the
            card until its own controls were pushed toward the fold of a
            bounded lane, which is the failure SupportLane's max-height note
            already records for four cards.
            
            The earlier steps are not lost. A TUTOR_SOLVED rescue writes each
            step onto the tutor layer as it arrives (see `writesToStudentCanvas`
            and `actionMarks`), which is the tutor working DOWN the page beside
            the student — so the worked column accumulates where it belongs,
            on the canvas, while the panel says the one thing to do now. */}
        <p
          key={current.actionId}
          className={
            current.answerReveal
              ? 'mt-2 text-[15px] font-semibold leading-snug text-slate-900'
              : 'mt-2 text-[15px] leading-snug text-slate-700'
          }
        >
          {current.text}
        </p>

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
