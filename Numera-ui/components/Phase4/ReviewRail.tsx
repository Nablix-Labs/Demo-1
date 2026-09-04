'use client';

/**
 * The Phase 3 journey, one row per question.
 *
 * §8.4: a correct question "may show completion status but do not launch a
 * Tutor Replay", so a row without a replay is a plain <div> — not focusable,
 * not pressable, no hover. A control that looks live and does nothing is worse
 * than no control, and this list is mostly such rows for a student who did
 * well.
 *
 * The number in the circle is the question's POSITION, never its id (§8.9,
 * §9.3). It is coloured by status so the rail can be read at a glance without
 * matching each row against the legend at the bottom.
 */

import { cn } from '@/lib/cn';
import { STATUS_LABEL, type JourneyRow, type JourneyStatus } from '@/lib/phase4Review';

/**
 * Status colours, defined once.
 *
 * Colour is never the only carrier: every row also prints the status word, and
 * the legend names all three. A student who cannot separate the amber from the
 * red still reads "Partial" and "Needs review".
 */
const STATUS: Record<JourneyStatus, { dot: string; text: string; badge: string }> = {
  correct: {
    dot: 'bg-emerald-500',
    text: 'text-emerald-600',
    badge: 'bg-emerald-500 text-white',
  },
  partial: {
    dot: 'bg-amber-500',
    text: 'text-amber-600',
    badge: 'bg-amber-500 text-white',
  },
  'needs-review': {
    dot: 'bg-red-500',
    text: 'text-red-600',
    badge: 'bg-red-500 text-white',
  },
};

const ORDER: JourneyStatus[] = ['correct', 'partial', 'needs-review'];

export default function ReviewRail({
  rows,
  activeReplayIndex,
  onSelect,
}: {
  rows: JourneyRow[];
  /** The replay currently on the board, or null while the summary is showing. */
  activeReplayIndex: number | null;
  onSelect: (replayIndex: number) => void;
}) {
  // Nothing to correct means no rail at all. A heading over an empty bordered
  // box announces a section and then shows nothing, which reads as a failure to
  // load rather than as "there was nothing to correct".
  if (rows.length === 0) return null;

  return (
    <nav aria-label="Questions in independent practice" className="flex flex-col gap-3">
      <h2 className="text-[13px] font-semibold text-ink px-0.5">
        Questions in independent practice
      </h2>

      <ol className="flex flex-col gap-2">
        {rows.map((row, i) => {
          const replayable = row.replayIndex !== null;
          const active = replayable && row.replayIndex === activeReplayIndex;
          const tone = STATUS[row.status];

          const body = (
            <>
              <span
                aria-hidden="true"
                className={cn(
                  'flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center',
                  'text-[12.5px] font-semibold',
                  tone.badge,
                )}
              >
                {i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[12.5px] font-semibold text-ink leading-tight">
                  {row.label}
                </span>
                {/* What the question TESTS, not the prompt — the row is far too
                    narrow for the prompt, and a truncated one reads as
                    "Which is the general rul…", which names nothing. Falls
                    back to the question text when the backend has authored no
                    label (lib/phase4Review). */}
                <span className="block text-[11.5px] text-slate-blue truncate mt-0.5">
                  {row.skillLabel}
                </span>
              </span>
              <span className={cn('flex-shrink-0 flex items-center gap-1.5 text-[11px] font-medium', tone.text)}>
                <span aria-hidden="true" className={cn('w-2 h-2 rounded-full', tone.dot)} />
                {STATUS_LABEL[row.status]}
              </span>
            </>
          );

          const shell =
            'w-full flex items-center gap-2.5 rounded-xl border bg-white px-3 py-2.5 text-left';

          return (
            <li key={i}>
              {replayable ? (
                <button
                  onClick={() => onSelect(row.replayIndex as number)}
                  aria-current={active ? 'true' : undefined}
                  className={cn(
                    shell,
                    'transition-colors',
                    active
                      ? 'border-focus-navy ring-1 ring-focus-navy/25 bg-focus-navy/[0.04]'
                      : 'border-muted-gray hover:border-slate-blue/50',
                  )}
                >
                  {body}
                </button>
              ) : (
                // Deliberately not a button: §8.4 forbids launching a replay
                // from a correct question, so there is nothing to press.
                <div className={cn(shell, 'border-muted-gray cursor-default')}>{body}</div>
              )}
            </li>
          );
        })}
      </ol>

      {/* The legend earns its place: three colours are only readable as a scale
          once something names them in order. */}
      <ul className="flex items-center gap-3 px-0.5 pt-1">
        {ORDER.map((status) => (
          <li key={status} className="flex items-center gap-1.5 text-[10.5px] text-slate-blue">
            <span aria-hidden="true" className={cn('w-2 h-2 rounded-full', STATUS[status].dot)} />
            {STATUS_LABEL[status]}
          </li>
        ))}
      </ul>
    </nav>
  );
}
