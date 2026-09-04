'use client';

/**
 * SupportLane — one column for everything the tutor is currently offering.
 *
 * The cue owned a `fixed` position of its own, which was fine while it was the
 * only card. Adding the hint at the same coordinates would have stacked one on
 * top of the other, and a hint hidden behind a cue is no more visible than a
 * hint in a collapsed panel — the bug this was meant to fix.
 *
 * So position lives HERE and the cards are ordinary blocks inside it. §5 of the
 * V1-Hybrid spec asks for exactly this: support appears in a lane beside the
 * workspace, not layered over it and not pushing the page down.
 *
 * Hint above cue, because that is the order the ladder serves them in (§6:
 * hint → visual cue → scaffold) — so a student who receives both reads them in
 * the order they were given. `pointer-events-none` on the column with the cards
 * re-enabling it: the empty lane must never swallow a click meant for canvas
 * underneath it.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { rescueActive } from '@/lib/rescueMode';
import { cn } from '@/lib/cn';
import WriteNote from '@/components/WriteNote';
import RescueNote from '@/components/RescueNote';
import RescueSteps from '@/components/RescueSteps';
import HintNote from '@/components/HintNote';
import VisualCue from '@/components/VisualCue';

export default function SupportLane() {
  const panelSide = useNumeraStore((s) => s.panelSide);
  /**
   * A rescue takes the lane to itself.
   *
   * The rungs above it — the write instruction, the hint, the cue — are the
   * ones that already failed this student; that is what being at the bottom of
   * the ladder means. Rendered beside a walkthrough they are three competing
   * instructions next to the one thing the tutor is actually doing, and the
   * lane is bounded, so they also push the rescue's own controls toward the
   * fold (see the max-height note below).
   *
   * The store clears them when a rescue opens. This is the render half, and it
   * is not redundant: support arrives on the same turn as the rescue action,
   * and some of it is applied AFTER the actions are — so without this gate a
   * cleared rung reappears on the very turn it was cleared.
   */
  const rescueOn = useNumeraStore(rescueActive);

  return (
    <div
      className={cn(
        // Below the "Explain it back" chrome, so it stacks under it, not over.
        'pointer-events-none fixed top-[84px] z-30 flex flex-col gap-3',
        // Bounded and scrollable, because the lane can now hold four cards.
        // With a write instruction, a hint, a cue and a worked example all up at
        // once the column ran 918px on a 900px window and the bottom card's
        // controls sat below the fold — "Back to the question" was on screen and
        // could not be clicked (measured, 18 Aug).
        //
        // Scrolling still works despite `pointer-events-none`: that only stops
        // the empty lane hit-testing, so a click with no card under it still
        // reaches the canvas, while a wheel over a card (which sets
        // `pointer-events-auto`) bubbles to this scroll container.
        //
        // `pr-2` and `overflow-x-hidden` together because setting overflow on
        // one axis forces the other to `auto` rather than leaving it visible.
        // The note's shadow overhangs its box by 4px, which was enough to put a
        // horizontal scrollbar under every card — 16px of grey, visible in the
        // live app. The padding gives the shadow room; the hidden axis stops
        // anything wider bringing the bar back.
        'max-h-[calc(100vh-104px)] overflow-y-auto overflow-x-hidden pr-2',
        // Opposite the tutor panel: the canvas keeps the middle.
        panelSide === 'right' ? 'left-4' : 'right-4',
      )}
    >
      {/* Above the ladder, not part of it: a WRITE instruction is the tutor
          saying it could not read the student, and it names the action that
          moves the turn on. Below a hint it would read as the least urgent
          thing on screen when it is the only one that unblocks them. */}
      {!rescueOn && (
        <>
          <div className="pointer-events-auto"><WriteNote /></div>
          <div className="pointer-events-auto"><HintNote /></div>
          <div className="pointer-events-auto"><VisualCue /></div>
        </>
      )}
      {/* Last in the lane because it is last on the ladder — a student who has
          reached a worked example has already been past the rungs above it. */}
      <div className="pointer-events-auto"><RescueNote /></div>
      {/* The same rung, on the step-at-a-time contract. Both are rendered here,
          but only one can ever have content: RescueNote stands down whenever a
          stepwise step exists (lib/rescueMode). That precedence used to be an
          ASSUMPTION about the backend — "it serves one or the other, never
          both" — and the two panels Chirudeva reported on 4 Sep are that
          assumption being wrong. It is now a rule the client enforces. */}
      <div className="pointer-events-auto"><RescueSteps /></div>
    </div>
  );
}
