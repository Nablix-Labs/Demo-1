'use client';

/**
 * The contents page.
 *
 * This used to be a sidebar of numbered cards, which is the shape every app
 * reaches for and reads as chrome bolted to the side of the notebook. A real
 * notebook does not have a sidebar — it has a contents page at the front, so
 * that is what this is: the same paper as the sheets, ruled the same way, with
 * entries running to dot leaders and page numbers.
 *
 * The current topic is marked by a ribbon tucked into the edge, the way you
 * would actually keep your place. A topic the session flagged carries its note
 * inline, because the thing a student got wrong today should be visible before
 * they choose what to open.
 */

import type { KeyNote } from '@/lib/keynotes';
import { NOISE } from './Page';
import { cn } from '@/lib/cn';

export default function TopicRail({
  notes,
  activeId,
  pageOf,
  onSelect,
}: {
  notes: KeyNote[];
  activeId: string;
  /** 1-based spread the topic opens on. */
  pageOf: (id: string) => number;
  onSelect: (id: string) => void;
}) {
  return (
    <nav
      aria-label="Contents"
      className="relative w-[238px] flex-shrink-0 rounded-[18px] bg-[#FDFBF7] px-6 pt-6 pb-7"
      style={{
        backgroundImage: NOISE,
        boxShadow:
          '0 1px 0 rgba(255,255,255,0.9) inset, 0 18px 40px -26px rgba(27,42,74,0.5)',
      }}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[1.4px] text-slate-blue/60">
        Contents
      </p>
      <div className="mt-1 mb-4 h-px bg-[#1B2A4A]/12" />

      <ul className="flex flex-col">
        {notes.map((note) => {
          const active = note.id === activeId;
          return (
            <li key={note.id} className="relative">
              {/* The place-keeping ribbon, tucked past the paper's edge. */}
              {active && (
                <span
                  aria-hidden="true"
                  className="absolute -left-6 top-[9px] h-5 w-[7px] rounded-r-[2px] bg-learning-blue"
                />
              )}

              <button
                onClick={() => onSelect(note.id)}
                aria-current={active ? 'true' : undefined}
                className="group w-full py-[7px] text-left"
              >
                <span className="flex items-baseline gap-1.5">
                  <span
                    className={cn(
                      'text-[13px] leading-snug transition-colors',
                      active
                        ? 'font-semibold text-ink'
                        : 'text-slate-blue group-hover:text-ink',
                    )}
                  >
                    {note.topic}
                  </span>

                  {/* Dot leader, as a printed contents page sets it. */}
                  <span
                    aria-hidden="true"
                    className="min-w-[10px] flex-1 translate-y-[-3px] border-b border-dotted border-[#1B2A4A]/25"
                  />

                  <span
                    className={cn(
                      'text-[11.5px] tabular-nums transition-colors',
                      active ? 'font-semibold text-learning-blue' : 'text-slate-blue/70',
                    )}
                  >
                    {pageOf(note.id)}
                  </span>
                </span>

                {note.flagged && (
                  <span className="mt-1 flex items-center gap-1.5 text-[10.5px] italic text-highlight-amber">
                    <span aria-hidden="true">✎</span>
                    You slipped here today
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
