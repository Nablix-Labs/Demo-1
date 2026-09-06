'use client';

/**
 * SupportDeck — one support card, and a way back to the earlier ones.
 *
 * Manjusha, 5 Sep: "only the latest one we should show […] only one at a time
 * (the latest) should be visible. The rear should be stacked, if the student
 * wants to see he can click and see."
 *
 * Which rung is showing is not decided here — `lib/supportDeck` owns that, so
 * this component cannot drift from the store the way five separate render-time
 * gates did before it. This is the presentation half only: render the one rung
 * it is told to, and offer the rest as chips.
 *
 * The cards are the existing ones, unchanged. Each already knows how to render
 * nothing when it has no content, so rendering only the visible rung is a
 * matter of not mounting the others — no new "is there anything to show" logic,
 * and no second opinion about it.
 */

import { useShallow } from 'zustand/react/shallow';
import { useNumeraStore } from '@/store/useNumeraStore';
import { visibleRung, collapsedRungs, rungLabel, type DeckRung } from '@/lib/supportDeck';
import HintNote from '@/components/HintNote';
import VisualCue from '@/components/VisualCue';
import RescueNote from '@/components/RescueNote';
import RescueSteps from '@/components/RescueSteps';

function Card({ rung }: { rung: DeckRung }) {
  switch (rung) {
    case 'HINT':
      return <HintNote />;
    case 'VISUAL_CUE':
      return <VisualCue />;
    // One rung, two implementations. Both are mounted because only one can ever
    // have content — RescueNote stands down whenever a stepwise step exists
    // (lib/rescueMode) — and that precedence is load-bearing: the legacy payload
    // carries every step including the answer the stepwise walkthrough is
    // releasing one at a time.
    case 'PARALLEL_EXAMPLE':
    case 'TUTOR_SOLVED':
      return (
        <>
          <RescueNote />
          <RescueSteps />
        </>
      );
  }
}

export default function SupportDeck() {
  // `visibleRung` returns a string or null, so Object.is settles it.
  const showing = useNumeraStore(visibleRung);
  // `collapsedRungs` builds a NEW array on every call, and zustand v5 compares
  // snapshots with Object.is — so selecting it bare made every read look like a
  // change, which is an unbounded re-render loop and React error #185
  // ("Maximum update depth exceeded"). It took the whole guided screen down
  // through the error boundary, for three testers, within an hour of shipping.
  // useShallow is what the rest of this codebase already uses for object and
  // array selectors, for exactly this reason.
  const earlier = useNumeraStore(useShallow(collapsedRungs));
  const openSupportRung = useNumeraStore((s) => s.openSupportRung);

  if (!showing && earlier.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      {showing && (
        <div className="pointer-events-auto">
          <Card rung={showing} />
        </div>
      )}

      {earlier.length > 0 && (
        <div className="pointer-events-auto w-[264px]">
          {/* Named rather than a row of bare chips: "Earlier help" says what
              the row IS. Without it the chips read as things to do next, which
              is the opposite of what they are. */}
          <div className="mb-1.5 text-[9.5px] font-bold uppercase tracking-[0.16em] text-slate-blue/70">
            Earlier help
          </div>
          <div className="flex flex-wrap gap-1.5">
            {earlier.map((rung) => (
              <button
                key={rung}
                onClick={() => openSupportRung(rung)}
                className="rounded-full border border-muted-gray bg-white/90 px-3 py-1.5 text-[11.5px]
                           font-semibold text-slate-blue shadow-sm transition-colors
                           hover:border-slate-blue hover:text-ink
                           focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/50"
              >
                {rungLabel(rung)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
