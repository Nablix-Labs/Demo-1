'use client';

/**
 * The Phase 3 question journey (§8.4, Left Pane).
 *
 * One bordered container with divided rows, which is how every list in this app
 * is built (the worksheet recap on this same route, the topic list, the history
 * screen). Five separately-bordered cards floating in a column reads as five
 * unrelated objects; this reads as one list of one student's questions.
 *
 * A correct question is a row, not a button: §8.4 says correct questions "may
 * show completion status but do not launch a Tutor Replay", and a control that
 * looks pressable and does nothing is worse than no control.
 *
 * No question ids and no micro-skill ids, per §8.9 and §9.3. The 18 Aug mockup
 * has both on every card; that divergence is raised with Sanya rather than
 * settled here.
 */

import { Check, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import type { JourneyRow } from '@/lib/phase4Review';

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
  return (
    <nav aria-label="Questions in independent practice">
      <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2.5">
        Independent practice
      </div>

      <div className="rounded-lg border border-muted-gray bg-white divide-y divide-muted-gray overflow-hidden">
        {rows.map((row, i) => {
          const replayable = row.replayIndex !== null;
          const active = replayable && row.replayIndex === activeReplayIndex;

          const body = (
            <>
              <span
                className={cn(
                  'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center',
                  row.status === 'correct'
                    ? 'bg-focus-navy text-white'
                    : 'border border-muted-gray text-slate-blue',
                )}
              >
                {row.status === 'correct'
                  ? <Check size={13} strokeWidth={2.4} />
                  : <X size={13} strokeWidth={2.4} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[12.5px] font-semibold text-ink leading-tight">
                  {row.label}
                </span>
                {/* The question itself, so the list is navigable by what was
                    asked rather than by a number the student never saw. */}
                <span className="block text-[11.5px] text-slate-blue truncate mt-0.5 font-[Cambria_Math,Georgia,serif]">
                  {row.questionText}
                </span>
              </span>
            </>
          );

          const shell = 'w-full flex items-center gap-3 px-4 py-3 text-left';

          return replayable ? (
            <button
              key={i}
              onClick={() => onSelect(row.replayIndex as number)}
              aria-current={active ? 'true' : undefined}
              className={cn(
                shell,
                'transition-colors',
                active ? 'bg-reading-surface' : 'hover:bg-reading-surface',
              )}
            >
              {/* The active marker is a rule down the edge rather than a border
                  round the row: a box inside a divided list breaks the list. */}
              <span
                aria-hidden="true"
                className={cn('-ml-4 mr-0 w-[3px] self-stretch rounded-r', active ? 'bg-focus-navy' : 'bg-transparent')}
              />
              {body}
            </button>
          ) : (
            // Deliberately a <div>: not focusable, not pressable, no hover.
            <div key={i} className={cn(shell, 'cursor-default')}>
              <span aria-hidden="true" className="-ml-4 mr-0 w-[3px] self-stretch" />
              {body}
            </div>
          );
        })}
      </div>
    </nav>
  );
}
