'use client';

/**
 * The structured replay board (PR #257).
 *
 * The backend now sends a closed set of typed elements and keeps the narration
 * short, so this surface — not the prose — carries the mathematics. Elements
 * render in the order they arrive, which is the order the tutor builds the
 * explanation in: show the pattern, brace what changes and what does not, cross
 * out what the student wrote, box the rule, then check it on one number.
 *
 * Two rules hold this together:
 *
 *   An unknown `kind` renders NOTHING rather than falling back to its text.
 *   The set is closed and discriminated, so an unknown kind means a backend
 *   ahead of this build — and printing a raw payload field at a student is a
 *   worse outcome than omitting one element of a walkthrough they are also
 *   hearing narrated.
 *
 *   Nothing here is derived from the narration. Everything drawn was authored
 *   as this element by the backend. Inferring which expression was wrong from
 *   prose is exactly the class of client-side re-decision that produced the
 *   duplicated rescue panels.
 */

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Star } from 'lucide-react';
import { cn } from '@/lib/cn';
import { braceFit, columnsAbove } from '@/lib/phase4BoardLayout';
import { boardMarkId, boardRevealMarks, type BoardBox } from '@/lib/phase4Board';
import { useTutorReveal } from '@/store/useTutorReveal';
import TutorHandOverlay from '@/components/Canvas/TutorHandOverlay';
import type { TutorElement } from '@/store/useNumeraStore';
import type { Phase4BoardElement } from '@/lib/api';

/** The tutor's hand. Same stack the canvas ink uses, so the two read as one voice. */
const HAND = '"Bradley Hand", "Segoe Script", "Comic Sans MS", cursive';

/**
 * A drawn curly brace.
 *
 * SVG with a non-scaling stroke rather than a `{` glyph: the glyph stretches to
 * its font box and cannot span an arbitrary width, so a brace over three
 * columns came out as a comma. `preserveAspectRatio="none"` lets one path
 * stretch across whatever the row above turned out to be.
 */
function Brace({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 10"
      preserveAspectRatio="none"
      aria-hidden
      className={cn('w-full h-2.5', className)}
    >
      <path
        d="M1,1 C1,6 4,6 8,6 L44,6 C48,6 50,7 50,9 C50,7 52,6 56,6 L92,6 C96,6 99,6 99,1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        vectorEffect="non-scaling-stroke"
        strokeLinecap="round"
      />
    </svg>
  );
}

function Element({
  element,
  columns,
}: {
  element: Phase4BoardElement;
  /** Columns in the row a brace sits over; 0 when there is nothing to align to. */
  columns: number;
}) {
  switch (element.kind) {
    case 'value_row':
      return (
        <div
          className="grid gap-x-6 justify-center text-center"
          style={{ gridTemplateColumns: `repeat(${element.values.length}, minmax(0, 1fr))` }}
        >
          {element.values.map((value, i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <span className="text-[30px] leading-none text-ink" style={{ fontFamily: HAND }}>
                {value}
              </span>
              <span aria-hidden className="text-focus-navy text-[18px] leading-none">↓</span>
              {/* One caption, repeated under each column: the backend sends a
                  single `arrow_label` for the row because it describes what
                  happens at every value, not a different thing at each. */}
              <span className="text-[13px] text-focus-navy" style={{ fontFamily: HAND }}>
                {element.arrow_label}
              </span>
            </div>
          ))}
        </div>
      );

    case 'brace': {
      const fit = braceFit(element.labels, columns);
      return (
        <div className="flex flex-col items-center gap-1 w-full max-w-[420px] mx-auto">
          <Brace className="text-emerald-600" />
          {fit.mode === 'columns' ? (
            <div
              className="grid gap-x-6 w-full text-center"
              style={{ gridTemplateColumns: `repeat(${fit.columns}, minmax(0, 1fr))` }}
            >
              {fit.labels.map((label, i) => (
                <span key={i} className="text-[19px] text-emerald-600" style={{ fontFamily: HAND }}>
                  {label}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-[17px] text-emerald-600" style={{ fontFamily: HAND }}>
              {fit.label}
            </span>
          )}
        </div>
      );
    }

    case 'expression':
      return (
        <p className="text-center text-[24px] text-ink" style={{ fontFamily: HAND }}>
          {element.text}
        </p>
      );

    case 'label':
      return (
        <p className="text-center text-[15px] text-slate-blue" style={{ fontFamily: HAND }}>
          {element.text}
        </p>
      );

    case 'struck':
      // Boxed AND struck through, which is how the design reads it — the box
      // makes it the student's own answer being pointed at, the line makes it
      // withdrawn. Marked up as <del> so it is withdrawn to a screen reader too,
      // not merely drawn with a line across it.
      return (
        <del className="mx-auto block w-fit rounded-md border-2 border-red-500 px-4 py-2 no-underline">
          <span
            className="text-[26px] text-red-500 line-through decoration-2"
            style={{ fontFamily: HAND }}
          >
            {element.text}
          </span>
        </del>
      );

    case 'boxed':
      return (
        <p
          className="mx-auto w-fit rounded-lg border-2 border-emerald-600 px-5 py-2.5
                     text-[26px] text-emerald-700"
          style={{ fontFamily: HAND }}
        >
          {element.text}
        </p>
      );

    case 'example':
      return (
        <p className="mx-auto flex w-fit items-center gap-2.5 rounded-lg bg-focus-navy/[0.06] px-4 py-2.5">
          <Star size={16} strokeWidth={2.2} className="flex-shrink-0 text-focus-navy" aria-hidden />
          {/* Authored with a newline between the substitution and the result;
              preserved rather than collapsed, because that break is what makes
              it read as a worked check instead of one long line. */}
          <span
            className="text-[19px] text-focus-navy whitespace-pre-line leading-snug"
            style={{ fontFamily: HAND }}
          >
            {element.text}
          </span>
        </p>
      );

    default:
      // An element kind this build does not know. Rendering nothing is
      // deliberate — see the note at the top of the file.
      return null;
  }
}

export default function ReplayBoard({
  elements,
  fallbackText,
  revealFrom = 0,
}: {
  elements: readonly Phase4BoardElement[];
  /**
   * How many leading elements were already on the board before this step.
   * Those sit at rest; the rest are written in by the handwriting engine —
   * the same reveal store and writing hand the Phase 1 canvas uses.
   */
  revealFrom?: number;
  /**
   * `tutor_write` for a step inside a boarded replay that has no board of its
   * own. Shown as the step's heading rather than switching the whole panel back
   * to the handwriting canvas mid-explanation.
   */
  fallbackText?: string;
}) {
  const boardRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  const marksRef = useRef<TutorElement[]>([]);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = boardRef.current;
    if (!node) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize((s) => (s.width === width && s.height === height ? s : { width, height }));
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, []);

  // Hand the new elements to the writing engine once they are laid out, and
  // wipe each one in as its progress advances — imperatively, since progress
  // ticks every frame and only these nodes care.
  useLayoutEffect(() => {
    const board = boardRef.current;
    if (!board) return;
    const origin = board.getBoundingClientRect();
    const boxes: BoardBox[] = elements.map((_, i) => {
      const r = itemRefs.current[i]?.getBoundingClientRect();
      return r
        ? { x: r.left - origin.left, y: r.top - origin.top + board.scrollTop, w: r.width, h: r.height }
        : { x: 0, y: 0, w: 0, h: 0 };
    });
    const marks = boardRevealMarks(elements, revealFrom, boxes, size.width, size.height);
    marksRef.current = marks;
    const reveal = useTutorReveal.getState();
    reveal.sync(marks);

    const paint = () => {
      const progress = useTutorReveal.getState().progress;
      elements.forEach((_, i) => {
        const node = itemRefs.current[i];
        if (!node) return;
        const p = i < revealFrom ? 1 : progress[boardMarkId(i)] ?? 0;
        // Pad top and bottom so ascenders and the box border are not shaved.
        node.style.clipPath = p >= 1 ? '' : `inset(-8px ${(1 - p) * 100}% -8px -8px)`;
      });
    };
    paint();
    const unsub = useTutorReveal.subscribe(paint);
    return () => { unsub(); useTutorReveal.getState().sync([]); };
  }, [elements, revealFrom, size]);

  if (elements.length === 0) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center p-6">
        <p className="text-[26px] text-ink text-center" style={{ fontFamily: HAND }}>
          {fallbackText ?? ''}
        </p>
      </div>
    );
  }

  return (
    <div ref={boardRef} className="relative flex-1 min-h-0 overflow-y-auto">
      <div className="flex flex-col items-stretch justify-center gap-4 min-h-full px-6 py-7">
        {elements.map((element, i) => (
          <div
            key={i}
            ref={(n) => { itemRefs.current[i] = n; }}
            // The nib is read from this box (`tipFor`, kind 'math'), so it has
            // to be the ink's width. A row and its brace keep the full width:
            // their columns align to the row, and their ink spans it anyway.
            data-tutor-math-id={boardMarkId(i)}
            className={cn(
              element.kind === 'value_row' || element.kind === 'brace'
                ? 'w-full'
                : 'w-fit max-w-full mx-auto',
            )}
          >
            <Element
              element={element}
              columns={element.kind === 'brace' ? columnsAbove(elements, i) : 0}
            />
          </div>
        ))}
      </div>
      <TutorHandOverlay width={size.width} height={size.height} marks={() => marksRef.current} />
    </div>
  );
}
