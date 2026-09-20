'use client';

/**
 * ScaffoldTrail — the guided steps as one line across the top of the page.
 *
 * Replaces the bordered ScaffoldPanel that sat between the question and the
 * canvas. Two things were wrong with that card:
 *
 *   1. It was a second block of text directly under the question, competing
 *      for the same slot and pushing the working area down.
 *   2. It showed one step and nothing else, so "Step 2 of 4" was a bare
 *      counter — a student could not see what they had already settled or how
 *      much was left. A scaffold IS a path; it was drawn as a notice.
 *
 * It was first built down the left margin, in the tutor's hand, like a
 * teacher's notes beside the working. That read well but cost 196px of page
 * WIDTH for as long as the scaffold was open, and width is what the student
 * writes in. Turned on its side it costs about 40px of height instead and
 * gives all of that back (Manav, 20 Sep 2026).
 *
 * The exercise-book hand stays — the steps are still written, not labelled,
 * and the amber rule under them is the ruled line at the top of a page rather
 * than the margin rule down its side.
 *
 * Three rules carried over from ScaffoldPanel, all still load-bearing:
 *
 *   - No counting. Step number and total come from the response; nothing is
 *     incremented locally, so this cannot drift from the Student Model.
 *   - Nothing hidden leaks. A step the backend has not released is drawn as a
 *     bare number — `total_scaffold_steps` is "a progress indicator, NOT
 *     permission to reveal later ones". `trailRows` enforces that; this only
 *     draws what it is handed.
 *   - It simply does not open when the backend sends no scaffold.
 */

import { Fragment } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { trailRows, type TrailRow } from '@/lib/scaffoldTrail';

// The variable next/font sets for Caveat (lib/tutorFont.ts). Read straight in
// CSS rather than through `tutorFontFamily()`, which resolves and caches a real
// family name for canvas measuring and would pin the fallback if it ran first.
const HAND = { fontFamily: 'var(--font-tutor-hand), cursive' } as const;

function Step({ row }: { row: TrailRow }) {
  if (row.state === 'pending') {
    return (
      <li
        style={HAND}
        className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full
                   border border-slate-blue/25 text-[14px] leading-none text-slate-blue/45"
      >
        {row.stepNumber}
      </li>
    );
  }

  if (row.state === 'done') {
    return (
      <li className="flex items-baseline gap-1.5 opacity-70">
        <span style={HAND} className="text-[15px] leading-none text-success-sage">
          {row.stepNumber}
        </span>
        <span
          style={HAND}
          className="text-[16px] leading-none text-success-sage line-through decoration-success-sage/70"
        >
          {row.stepText}
        </span>
      </li>
    );
  }

  return (
    <li className="flex items-baseline gap-2">
      <span style={HAND} className="text-[19px] leading-none text-action-orange">
        {row.stepNumber}
      </span>
      {/* Underlined with text-decoration rather than a border: a border on an
          inline box draws once per line box, so a step that wrapped got a
          full-width rule under line one and a stub under line two. */}
      <span
        style={HAND}
        className="text-[21px] leading-tight text-focus-navy underline
                   decoration-highlight-amber/70 decoration-2 underline-offset-4"
      >
        {row.stepText}
      </span>
    </li>
  );
}

/** Between steps: the dotted run of a pencil line, not a UI divider. */
function Link() {
  return (
    <li
      aria-hidden
      className="h-px w-5 flex-shrink-0 self-center"
      style={{
        backgroundImage:
          'repeating-linear-gradient(90deg, rgba(74,105,132,.4) 0 3px, transparent 3px 7px)',
      }}
    />
  );
}

export default function ScaffoldTrail() {
  const scaffold = useNumeraStore((s) => s.activeScaffold);
  const seen = useNumeraStore((s) => s.scaffoldSeen);
  const rows = trailRows(seen, scaffold);

  if (!rows.length) return null;

  return (
    <ol
      className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 border-b-2
                 border-highlight-amber/45 pb-2 pr-[150px]"
      aria-label="Guided steps"
      // Announced politely so a screen-reader user hears a new step without it
      // interrupting the tutor's own message.
      aria-live="polite"
    >
      {rows.map((row, i) => (
        // A pencil run before every step but the first. Keyed off the step
        // number, which `trailRows` guarantees is unique across the trail.
        <Fragment key={row.stepNumber}>
          {i > 0 && <Link />}
          <Step row={row} />
        </Fragment>
      ))}
    </ol>
  );
}
