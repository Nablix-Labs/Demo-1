'use client';

/**
 * A run of question text with the tutor's anchors drawn on it (Chirudeva
 * handoff §1).
 *
 * The label is rendered inline, immediately after the span it belongs to,
 * rather than as an arrow floating above it. An arrow needs absolute
 * positioning against a measured glyph, and the question wraps — at a line
 * break the arrow lands on the wrong word or off the edge entirely, which is
 * the same failure as highlighting the wrong token. Inline, it wraps with the
 * text it describes and cannot separate from it.
 *
 * `from`/`to` are the span of `question` this component is drawing, because the
 * layout renders the question in fragments (a grid of cases, then the
 * instruction after it) and each fragment must only show its own anchors.
 */

import { anchorSegments, type QuestionAnchor } from '@/lib/questionAnchors';

export default function AnchoredText({
  question,
  anchors,
  from,
  to,
}: {
  /** The full `current_question` the offsets index into. */
  question: string;
  anchors: QuestionAnchor[] | null | undefined;
  from?: number;
  to?: number;
}) {
  const segments = anchorSegments(question, anchors, from, to);

  // Nothing anchored in this fragment: render it as plain text, so an ordinary
  // question carries no extra markup at all.
  if (segments.every((s) => s.anchor === null)) {
    return <>{segments.map((s) => s.text).join('')}</>;
  }

  return (
    <>
      {segments.map((segment, i) =>
        segment.anchor === null ? (
          <span key={i}>{segment.text}</span>
        ) : (
          <span key={i} className="relative inline whitespace-nowrap">
            <mark
              // `mark` rather than a styled span: a screen reader announces it
              // as marked text, which is the whole meaning here.
              className="rounded-[3px] bg-highlight-amber/25 px-[2px] py-[1px] text-ink"
            >
              {segment.text}
            </mark>
            {segment.anchor.label && (
              <span
                className="ml-1 align-middle rounded-full bg-highlight-amber/15 px-1.5 py-[1px] text-[10px] font-semibold tracking-wide text-slate-blue"
                // Read out as part of the sentence it annotates, not as a
                // stray fragment after it.
                aria-label={`${segment.text}: ${segment.anchor.label}`}
              >
                {segment.anchor.label}
              </span>
            )}
          </span>
        ),
      )}
    </>
  );
}
