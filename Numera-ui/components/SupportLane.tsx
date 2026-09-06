'use client';

/**
 * SupportLane — one column for everything the tutor is currently offering.
 *
 * The cue owned a `fixed` position of its own, which was fine while it was the
 * only card. Adding the hint at the same coordinates would have stacked one on
 * top of the other, so position lives HERE and the cards are ordinary blocks
 * inside it. §5 of the V1-Hybrid spec asks for exactly this: support appears in
 * a lane beside the workspace, not layered over it and not pushing the page
 * down.
 *
 * The lane used to render the ladder itself — write note, hint, cue, then the
 * two rescue cards — and enforce ONE exclusion rule of its own (a rescue takes
 * the lane). That left the write note, the hint and the cue with no mutual
 * exclusion at all: all three could stand at once, and with a worked example
 * beside them the column measured 918px in a 900px window, putting the bottom
 * card's controls below the fold where they could not be clicked (18 Aug).
 *
 * Now the lane only positions. `lib/supportDeck` decides what is on screen and
 * SupportDeck renders it, so there is one answer to "what support is showing"
 * instead of a rule here and two more in the store.
 *
 * `pointer-events-none` on the column with the cards re-enabling it: the empty
 * lane must never swallow a click meant for the canvas underneath it.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';
import WriteNote from '@/components/WriteNote';
import SupportDeck from '@/components/SupportDeck';

export default function SupportLane() {
  const panelSide = useNumeraStore((s) => s.panelSide);

  return (
    <div
      className={cn(
        // Below the "Explain it back" chrome, so it stacks under it, not over.
        'pointer-events-none fixed top-[84px] z-30 flex flex-col gap-3',
        // Still bounded and scrollable. The deck should make the overflow
        // impossible — one card instead of four — but a single long walkthrough
        // on a short window can still run past the fold, and removing the cap
        // would be removing a fix rather than finishing one.
        //
        // Scrolling still works despite `pointer-events-none`: that only stops
        // the empty lane hit-testing, so a click with no card under it still
        // reaches the canvas, while a wheel over a card (which sets
        // `pointer-events-auto`) bubbles to this scroll container.
        //
        // `pr-2` and `overflow-x-hidden` together because setting overflow on
        // one axis forces the other to `auto` rather than leaving it visible.
        // The note's shadow overhangs its box by 4px, which was enough to put a
        // horizontal scrollbar under every card.
        'max-h-[calc(100vh-104px)] overflow-y-auto overflow-x-hidden pr-2',
        // Opposite the tutor panel: the canvas keeps the middle.
        panelSide === 'right' ? 'left-4' : 'right-4',
      )}
    >
      {/* An INSTRUCTION, not an offer, so it is never collapsed into the deck:
          a WRITE instruction is the tutor saying it could not read the student,
          and it names the action that moves the turn on. Below a hint it would
          read as the least urgent thing on screen when it is the only one that
          unblocks them. */}
      <div className="pointer-events-auto"><WriteNote /></div>
      {/* Everything the tutor has OFFERED — one card, earlier ones as chips. */}
      <SupportDeck />
    </div>
  );
}
