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
import { DrawablyButton } from 'drawably/react';
import 'drawably/style.css';
import HintNote from '@/components/HintNote';
import VisualCue from '@/components/VisualCue';

function Card({ rung }: { rung: DeckRung }) {
  switch (rung) {
    case 'HINT':
      return <HintNote />;
    case 'VISUAL_CUE':
      return <VisualCue />;
    // Presented on the CANVAS, not here — see `railRungs`. `visibleRung` can no
    // longer return either, so this is unreachable; it stays as an explicit
    // answer rather than a fallthrough, because a new rung added to DeckRung
    // should fail the switch's exhaustiveness check and not land in the column
    // by default.
    case 'PARALLEL_EXAMPLE':
    case 'TUTOR_SOLVED':
      return null;
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
        <div>
          <Card rung={showing} />
        </div>
      )}

      {earlier.length > 0 && (
        <div className="w-[264px]">
          {/* Named rather than a row of bare chips: "Earlier help" says what
              the row IS. Without it the chips read as things to do next, which
              is the opposite of what they are. */}
          <div className="mb-1.5 text-[9.5px] font-bold uppercase tracking-[0.16em] text-slate-blue/70">
            Earlier help
          </div>
          <div className="flex flex-wrap gap-1.5">
            {earlier.map((rung) => (
              // Drawn rather than a CSS pill. These sit directly under the
              // tutor's paper notes, and a crisp bordered chip beside a
              // hand-drawn note read as a different product's control.
              //
              // `boil={0}` renders ONE static path instead of the library's
              // default three-frame flicker. A chip that never stops moving
              // beside a canvas a student is writing on competes with the
              // writing; the sketch is the point here, the motion is not.
              // (The library also freezes itself under prefers-reduced-motion.)
              //
              // It decorates a real <button>, so the keyboard and screen-reader
              // behaviour is the element's own, not a reimplementation.
              <DrawablyButton
                key={rung}
                onClick={() => openSupportRung(rung)}
                tone="neutral"
                boil={0}
                className="px-3 py-1.5 text-[11.5px] font-semibold text-slate-blue hover:text-ink"
              >
                {rungLabel(rung)}
              </DrawablyButton>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
