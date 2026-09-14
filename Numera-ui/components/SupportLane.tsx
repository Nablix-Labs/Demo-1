'use client';

/**
 * SupportLane — one column for everything the tutor is currently offering.
 *
 * The cue owned a `fixed` position of its own, which was fine while it was the
 * only card. Adding the hint at the same coordinates would have stacked one on
 * top of the other, so position lives HERE and the cards are ordinary blocks
 * inside it. §5 of the V1-Hybrid spec asks for exactly this: support appears in
 * a lane BESIDE the workspace, not layered over it — which is what this now
 * finally does. The lane was `fixed … right-4` for months, so every card sat on
 * top of the canvas and covered the tutor's own written working (Manjusha,
 * 4 Sep; `rescueColumn.test.ts` records the same frame). `RESCUE_WRAP_WIDTH`
 * exists only to bound the tutor's ink so it stops short of these cards, which
 * is compensation for the overlay rather than a fix for it.
 *
 * The column is RESERVED whether or not it has anything in it, and that is the
 * load-bearing part. The store holds raw Konva pixels — DrawingCanvas
 * normalises only on export — so a canvas that changed width when a hint
 * arrived would leave every existing stroke at its old pixel offsets and clip
 * the student's working off the right-hand edge mid-lesson. A constant width
 * costs some empty space and cannot move ink.
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
 * There is no `pointer-events-none` dance any more either. That existed so an
 * empty overlay could not swallow a click meant for the canvas underneath it;
 * nothing is underneath it now.
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
        // An ordinary flex child beside the canvas, which is `flex-1 min-w-0`
        // and so simply takes the rest. Nothing here is positioned over the
        // work surface any more.
        'w-[320px] shrink-0 flex flex-col gap-3 px-4 pt-4',
        // Clear of the "Need help?" pill, which is global chrome pinned
        // `fixed bottom-6 right-4` and therefore lands at the foot of this
        // column. That reads correctly — this is the help column — but a card
        // scrolled to the bottom would sit underneath it.
        'pb-24',
        'border-muted-gray bg-reading-surface',
        // Still scrollable. The deck should make overflow impossible — one card
        // instead of four — but a single long walkthrough on a short window can
        // still run past the fold.
        //
        // `overflow-x-hidden` because setting overflow on one axis forces the
        // other to `auto` rather than leaving it visible, and the note's shadow
        // overhangs its box by 4px — enough to put a horizontal scrollbar under
        // every card.
        'overflow-y-auto overflow-x-hidden',
        // Opposite the tutor panel: the canvas keeps the middle.
        panelSide === 'right' ? 'order-first border-r' : 'border-l',
      )}
    >
      {/* An INSTRUCTION, not an offer, so it is never collapsed into the deck:
          a WRITE instruction is the tutor saying it could not read the student,
          and it names the action that moves the turn on. Below a hint it would
          read as the least urgent thing on screen when it is the only one that
          unblocks them. */}
      <WriteNote />
      {/* Everything the tutor has OFFERED — one card, earlier ones as chips. */}
      <SupportDeck />
    </div>
  );
}
