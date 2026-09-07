'use client';

/**
 * InterventionPaused — "someone is looking at this for you".
 *
 * Spec: "Phase 3 Repeated Failure & Prerequisite Remediation", 5 Sep 2026, §10.
 * The topic is marked INTERVENTION_REQUIRED and "the automated learning route
 * pauses until the intervention is reviewed/resolved". Every learning route
 * 409s until then — answers, canvas checks, orientation, rescue, review
 * (Chirudeva, 7 Sep) — so there is genuinely nothing here for the student to
 * press.
 *
 * That is precisely why this exists. A screen with no explanation and dead
 * controls is the 4 Sep stranding bug: the student cannot tell "paused for me"
 * from "broken", and the only signal they get is that nothing works. This says
 * which it is.
 *
 * Two things it deliberately does NOT do:
 *
 *   - Blame or grade. By the time this shows, the student has failed the same
 *     question four times and been sent back through two topics. The pause is
 *     the system reaching its limit, not the student reaching theirs, and the
 *     wording has to carry that.
 *   - Offer a retry. Retrying is exactly what will not work, and a button that
 *     re-fails is worse than no button. The way out is a person.
 */

import { PauseCircle } from 'lucide-react';

export default function InterventionPaused() {
  return (
    <div
      role="status"
      className="mx-auto max-w-md rounded-2xl border border-muted-gray bg-white/95 px-6 py-6 text-center shadow-sm"
    >
      <PauseCircle className="mx-auto mb-3 h-7 w-7 text-slate-blue" aria-hidden />
      <h2 className="font-serif text-[19px] text-ink">This topic is paused for now</h2>
      <p className="mt-2 text-[13.5px] leading-relaxed text-slate-blue">
        {/* Says what became of the thing they were just asked for. This screen
            is only ever reached by answering the popup — a paused student who
            has not answered it yet is still being asked — so without it the
            popup closing onto a dead screen reads as the submission failing. */}
        Thanks for telling me what was tricky — I’ve passed it on. Your teacher
        will take a look and get this moving again.
      </p>
      <p className="mt-3 text-[12.5px] text-slate-blue/80">
        Nothing you did went wrong, and none of your work is lost.
      </p>
    </div>
  );
}
