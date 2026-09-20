'use client';

/**
 * ScaffoldMargin — the guided steps written down the margin of the page.
 *
 * Replaces the bordered ScaffoldPanel that sat between the question and the
 * canvas. Two things were wrong with that card, and the margin answers both:
 *
 *   1. It was a second box of text directly under the question, competing for
 *      the same slot and pushing the working area down.
 *   2. It showed one step and nothing else, so "Step 2 of 4" was a bare
 *      counter — a student could not see what they had already settled or how
 *      much was left. A scaffold IS a path; it was drawn as a notice.
 *
 * So the steps go where a teacher writes them: down the left margin of the
 * page, in the tutor's own hand, beside the working they refer to. The
 * metaphor is the one the canvas already uses — grid paper — and the
 * rule line is the margin rule of an exercise book.
 *
 * Three rules carried over from ScaffoldPanel, all still load-bearing:
 *
 *   - No counting. Step number and total come from the response; nothing is
 *     incremented locally, so this cannot drift from the Student Model.
 *   - Nothing hidden leaks. A step the backend has not released is drawn as a
 *     bare number — `total_scaffold_steps` is "a progress indicator, NOT
 *     permission to reveal later ones". `trailRows` enforces that; this only
 *     draws what it is handed.
 *   - The panel simply does not open when the backend sends no scaffold.
 *
 * `pointer-events-none` throughout: the canvas is underneath and the student
 * must be able to draw across this whole column. They will not want to — that
 * is what a margin is for — but the pen must never be blocked by it.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { trailRows, type TrailRow } from '@/lib/scaffoldTrail';

// The variable next/font sets for Caveat (lib/tutorFont.ts). Read straight in
// CSS rather than through `tutorFontFamily()`, which resolves and caches a real
// family name for canvas measuring and would pin the fallback if it ran first.
const HAND = { fontFamily: 'var(--font-tutor-hand), cursive' } as const;

function Row({ row }: { row: TrailRow }) {
  const hand = HAND;

  if (row.state === 'pending') {
    return (
      <li className="flex items-start gap-2 opacity-30">
        <span style={hand} className="text-[17px] leading-[1.1] text-slate-blue w-[13px] flex-shrink-0">
          {row.stepNumber}
        </span>
        {/* Deliberately blank. The count is public, the wording is not. */}
        <span className="mt-[9px] h-px flex-grow bg-slate-blue/35" aria-hidden />
      </li>
    );
  }

  if (row.state === 'done') {
    return (
      <li className="flex items-start gap-2 opacity-60">
        <span style={hand} className="text-[17px] leading-[1.1] text-success-sage w-[13px] flex-shrink-0">
          {row.stepNumber}
        </span>
        <span style={hand} className="text-[17px] leading-[1.15] text-success-sage line-through decoration-success-sage/70">
          {row.stepText}
        </span>
      </li>
    );
  }

  return (
    <li className="flex items-start gap-2">
      <span style={hand} className="text-[22px] leading-[1.05] text-action-orange w-[13px] flex-shrink-0">
        {row.stepNumber}
      </span>
      {/* Underlined with text-decoration rather than a border: a border on an
          inline box draws once per line box, so a step that wrapped got a
          full-width rule under line one and a stub under line two. This
          underlines each line to its own width, which is what underlining two
          lines of handwriting looks like. */}
      <span
        style={hand}
        className="text-[22px] leading-[1.3] text-focus-navy underline decoration-highlight-amber/70
                   decoration-2 underline-offset-4"
      >
        {row.stepText}
      </span>
    </li>
  );
}

export default function ScaffoldMargin() {
  const scaffold = useNumeraStore((s) => s.activeScaffold);
  const seen = useNumeraStore((s) => s.scaffoldSeen);
  const rows = trailRows(seen, scaffold);

  if (!rows.length) return null;

  return (
    <div
      className="pointer-events-none absolute left-0 top-[104px] bottom-0 w-[196px] z-[2]
                 border-r-2 border-highlight-amber/45 bg-white/70 backdrop-blur-[1px]"
      aria-label="Guided steps"
      // Announced politely so a screen-reader user hears a new step without it
      // interrupting the tutor's own message.
      aria-live="polite"
    >
      {/* The band itself starts below the question strip (top-[26px] over this
          same canvas) rather than running behind it. */}
      <ol className="flex flex-col gap-[18px] px-[15px] pt-[16px]">
        {rows.map((row) => (
          <Row key={row.stepNumber} row={row} />
        ))}
      </ol>
    </div>
  );
}
