'use client';

/**
 * ScaffoldPanel — the one guiding question the backend has authorised.
 *
 * Phase 2 support (frontend handoff, 2026-07-29). Three rules, all from §2 and
 * §9 of that document, and all of them are the reason this component is so
 * small:
 *
 *   1. One step. The Student Model holds the whole scaffold; the Tutor releases
 *      a single step at a time. This renders exactly what it is given and has
 *      no notion of a "next" step to advance to.
 *   2. No counting. Step number and total come from the response. Incrementing
 *      locally would drift out of step with the persisted Student Model — the
 *      specific failure §2 warns about.
 *   3. Nothing hidden leaks. It receives only `ActiveScaffold`, which carries
 *      no expected response, no canonical answer and no catalogue, so there is
 *      nothing here that could be rendered by mistake.
 *
 * "Step 2 of 3" is shown deliberately: the handoff calls the total a progress
 * indicator, and a student who knows there are three questions coming is less
 * likely to read the second one as failure.
 */

import { Compass } from 'lucide-react';
import type { ActiveScaffold } from '@/lib/api';

export default function ScaffoldPanel({ scaffold }: { scaffold: ActiveScaffold | null }) {
  if (!scaffold) return null;

  return (
    <section
      className="rounded-xl border-2 border-learning-blue/35 bg-white px-5 py-4"
      aria-label="Guided step"
      // Announced politely so a screen-reader user hears the new step without
      // it interrupting the tutor's own message.
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-learning-blue">
          <Compass size={14} strokeWidth={2} aria-hidden />
          Guided step
        </span>
        <span className="text-[11px] font-semibold text-slate-blue tabular-nums">
          Step {scaffold.stepNumber} of {scaffold.totalSteps}
        </span>
      </div>

      <p className="text-[16px] font-medium leading-snug text-ink">{scaffold.stepText}</p>
    </section>
  );
}
