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

import { DrawablyHighlight } from 'drawably/react';
import 'drawably/style.css';
import { anchorSegments, type QuestionAnchor } from '@/lib/questionAnchors';

/**
 * A stable sketch seed for a token.
 *
 * Without one, `drawably` picks a fresh random seed on every mount and the
 * wash under a word redraws itself whenever the turn re-renders — which on
 * this component is every tutor reply. The anchor is not changing, so neither
 * should its drawing.
 */
function seedFor(tokenId: string): number {
  let hash = 0;
  for (let i = 0; i < tokenId.length; i += 1) {
    hash = (hash * 31 + tokenId.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

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
        ) : !segment.anchor.label && !segment.anchor.highlighted ? (
          <span key={i}>{segment.text}</span>
        ) : (
          <span key={i} className="relative inline whitespace-nowrap">
            {/* A drawn marker wash rather than a CSS background, because that
                is what a tutor pointing at a word actually does. `drawably`
                gives a decoration that wraps one drawing PER LINE, which is
                the failure this file's header warns about for floating
                arrows — the wash cannot separate from the word it is on.

                Wrapping the <mark> rather than replacing it: DrawablyHighlight
                renders a <span> and takes no `as`, and the element is the whole
                point here — a screen reader announces marked text, which is the
                meaning. So the semantics stay and the drawing goes behind them.

                `boil={0}` for one static path. This sits inside the question a
                student is reading; flickering the word they are trying to read
                is the one place motion is clearly wrong. `seed` is derived from
                the token so the wash is stable across re-renders instead of
                re-drawing itself every time the turn updates. */}
            <DrawablyHighlight
              boil={0}
              seed={seedFor(segment.anchor.token_id)}
              fill="var(--drawably-anchor-wash)"
            >
              <mark
                // Background comes from the drawn wash now; a CSS fill behind it
                // too would print one highlight on top of another.
                className="bg-transparent px-[2px] py-[1px] text-ink"
              >
                {segment.text}
              </mark>
            </DrawablyHighlight>
            {segment.anchor.label && (
              // Deliberately NOT drawn, though the wash beside it is.
              // `DrawablyBadge` was tried here and is the wrong component: it
              // hard-codes `Geist Mono, ui-monospace` at 12px, because a badge
              // in that library is a kbd-style chip. This label is the tutor's
              // words about a word — prose, not a code token — and in monospace
              // inside a sentence it reads as machine output.
              //
              // The drawn box was also heavier than the mark it annotates,
              // which inverts the hierarchy: the WORD is what the student
              // should look at, and the label is the aside.
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
