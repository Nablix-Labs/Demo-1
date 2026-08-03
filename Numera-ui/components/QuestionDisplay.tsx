'use client';

/**
 * How a question appears on screen.
 *
 * One component rather than three copies of the same conditional, because the
 * screens had already drifted: the lesson canvas, independent practice and the
 * diagnostic each re-implemented "is this an equation or prose?" slightly
 * differently, and none of them handled a stack of cases at all.
 *
 * The layout decision itself is in lib/questionText.ts — this only draws it.
 */

import { questionLayout } from '@/lib/questionText';

// Set via `style` rather than an arbitrary Tailwind class: the class would have
// to be interpolated, and Tailwind's scanner only sees class strings written out
// literally — an interpolated one silently produces no CSS at all.
const MATHS_FONT = { fontFamily: 'Cambria Math, Georgia, serif' } as const;

export default function QuestionDisplay({
  question,
  size = 'lesson',
}: {
  question: string;
  /** `lesson` is the full canvas header; `compact` is the practice header. */
  size?: 'lesson' | 'compact';
}) {
  const layout = questionLayout(question);
  const equationSize = size === 'lesson' ? 'text-[22px]' : 'text-[16px]';
  const proseSize = size === 'lesson' ? 'text-[17px]' : 'text-[14px]';

  if (layout.kind === 'equation') {
    return (
      <div className={`${equationSize} font-semibold text-ink`}>
        Solve for <span className="italic" style={MATHS_FONT}>x</span>:{' '}
        <span style={MATHS_FONT}>{layout.text}</span>
      </div>
    );
  }

  if (layout.kind === 'cases') {
    // §3: "The alignment itself should reveal that the left values change while
    // +5 remains fixed." Columns are right-aligned so units digits line up —
    // 14 sits under 9, not one character to its right — and tabular numerals
    // keep every digit the same width regardless of the glyphs involved.
    const columns = layout.rows[0].length;
    return (
      <div
        className={`${equationSize} font-semibold text-ink inline-grid gap-x-4 gap-y-1 tabular-nums`}
        style={{ ...MATHS_FONT, gridTemplateColumns: `repeat(${columns}, auto)` }}
        role="group"
        aria-label="Cases to compare"
      >
        {layout.rows.map((row, r) =>
          row.map((cell, c) => (
            <span key={`${r}-${c}`} className="text-right">
              {cell}
            </span>
          )),
        )}
      </div>
    );
  }

  // Prose. `whitespace-pre-line` keeps any line breaks the backend sent — they
  // are deliberate, and collapsing them is what flattened the stacked cases in
  // the first place — while still letting long lines wrap.
  return (
    <p
      className={`${proseSize} font-semibold text-ink leading-snug max-w-[62ch] whitespace-pre-line`}
    >
      {layout.text}
    </p>
  );
}
