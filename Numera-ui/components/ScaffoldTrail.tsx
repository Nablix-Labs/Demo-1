'use client';

/**
 * ScaffoldTrail — the guided steps written along the line under the question.
 *
 * Replaces the bordered ScaffoldPanel that used to sit here. Two things were
 * wrong with that card:
 *
 *   1. It was a second block of text directly under the question, competing
 *      for the same slot and pushing the working area down.
 *   2. It showed one step and nothing else, so "Step 2 of 4" was a bare
 *      counter — a student could not see what they had already settled or how
 *      much was left. A scaffold IS a path; it was drawn as a notice.
 *
 * ── The rule IS the progress bar ──────────────────────────────────────────
 *
 * The first horizontal attempt set the steps in a row with dotted runs
 * between them and a rule underneath the lot. It read as clutter: four type
 * sizes, dashes that looked like debris, and two amber lines fighting a few
 * pixels apart.
 *
 * So there is one line, not a row of parts. Each step owns the segment of it
 * directly beneath, and the segment's colour says where the student is —
 * settled behind them, amber under the step they are on, faint ahead. Nothing
 * connects the steps because nothing has to: the line already does, the way a
 * ruled line on paper carries a sentence.
 *
 * ── Why two faces ─────────────────────────────────────────────────────────
 *
 * The current step is the tutor ASKING, so it is in the tutor's hand at
 * reading size. A settled step is a RECORD of something already answered, so
 * it is small and typeset — quiet enough to scan past, legible enough to
 * recall. Handwriting at 12px is neither.
 *
 * Three rules carried over from ScaffoldPanel, all still load-bearing:
 *
 *   - No counting. Step number and total come from the response; nothing is
 *     incremented locally, so this cannot drift from the Student Model.
 *   - Nothing hidden leaks. A step the backend has not released shows its
 *     number and no words — `total_scaffold_steps` is "a progress indicator,
 *     NOT permission to reveal later ones". `trailRows` enforces that; this
 *     only draws what it is handed.
 *   - It simply does not open when the backend sends no scaffold.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { trailRows, type TrailRow } from '@/lib/scaffoldTrail';

// The variable next/font sets for Caveat (lib/tutorFont.ts). Read straight in
// CSS rather than through `tutorFontFamily()`, which resolves and caches a real
// family name for canvas measuring and would pin the fallback if it ran first.
const HAND = { fontFamily: 'var(--font-tutor-hand), cursive' } as const;

/** Each step's own segment of the line. Butted together, so it reads as one. */
const RULE: Record<TrailRow['state'], string> = {
  done: 'border-success-sage/70',
  current: 'border-highlight-amber',
  pending: 'border-muted-gray',
};

function Tick() {
  return (
    <svg
      width="11" height="11" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"
      className="flex-shrink-0" aria-hidden
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Step({ row }: { row: TrailRow }) {
  const seg = `flex items-end border-b-[3px] ${RULE[row.state]} pb-[7px]`;

  if (row.state === 'pending') {
    return (
      <li className={`${seg} w-[34px] flex-shrink-0 justify-center`}>
        <span className="text-[12px] font-semibold leading-none text-slate-blue/35 tabular-nums">
          {row.stepNumber}
        </span>
      </li>
    );
  }

  if (row.state === 'done') {
    return (
      <li className={`${seg} flex-shrink-0 gap-1.5 pr-4`}>
        <span className="text-success-sage"><Tick /></span>
        <span className="text-[12.5px] leading-none text-slate-blue">{row.stepText}</span>
      </li>
    );
  }

  // The one the student is on: the tutor's own hand, at reading size. It alone
  // may wrap — truncating the question being asked would be worse than a
  // second line — so the band grows and every segment stays aligned to it.
  return (
    <li className={`${seg} min-w-0 flex-shrink gap-2 pr-5`}>
      <span
        style={HAND}
        className="text-[13px] font-semibold leading-none text-action-orange"
      >
        {row.stepNumber}
      </span>
      <span style={HAND} className="text-[21px] leading-[1.05] text-focus-navy">
        {row.stepText}
      </span>
    </li>
  );
}

export default function ScaffoldTrail() {
  const scaffold = useNumeraStore((s) => s.activeScaffold);
  const seen = useNumeraStore((s) => s.scaffoldSeen);
  const rows = trailRows(seen, scaffold);

  if (!rows.length) return null;

  return (
    <ol
      // Full width, unlike the question row above it, which reserves 150px for
      // "Explain it back". That button is pinned at top-[22px] and is ~38px
      // tall; the trail sits below the question, from about 66px down, so it
      // already clears it — and a rule that stopped short of the page edge
      // read as unfinished rather than as a ruled line.
      className="mt-3 flex items-stretch"
      aria-label="Guided steps"
      // Announced politely so a screen-reader user hears a new step without it
      // interrupting the tutor's own message.
      aria-live="polite"
    >
      {rows.map((row) => (
        <Step key={row.stepNumber} row={row} />
      ))}
      {/* Runs the line out to the edge of the page, so it reads as a ruled
          line the steps are written on rather than as a bar that stops. */}
      <li className="flex-grow border-b-[3px] border-muted-gray" aria-hidden />
    </ol>
  );
}
