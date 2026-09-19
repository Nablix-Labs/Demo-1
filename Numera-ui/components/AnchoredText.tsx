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
import { anchorSegments, usableAnchors, type QuestionAnchor } from '@/lib/questionAnchors';

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
            {/* The label is NOT written here. It used to be an inline chip
                immediately after the word, which reads acceptably in prose but
                breaks an expression in half: "In m + 7" rendered as
                "In m ⟨changes⟩ + 7", and the chip sits where a term belongs
                (Manjusha, 19 Sep 2026 — she circled it in green on the
                screenshot). The labels are collected under the question by
                `AnchorLegend` instead, where they cannot land inside the
                maths. */}
          </span>
        ),
      )}
    </>
  );
}

/**
 * The tutor's labels for this question, gathered under it.
 *
 * One line rather than a chip per word, for the reason above: the question is
 * a sentence — sometimes an equation — and nothing may be inserted into the
 * middle of it. Here the token is repeated beside its label, so "m — changes"
 * stands on its own and reads in the same order the student met the words in.
 *
 * Rendered once per question, not per fragment, because a legend split across
 * a grid of cases would repeat under every cell.
 */
export function AnchorLegend({
  question,
  anchors,
}: {
  question: string;
  anchors: QuestionAnchor[] | null | undefined;
}) {
  // `usableAnchors` orders by position and drops the unrenderable, so the
  // legend lists exactly the tokens that are washed above it, left to right.
  const labelled = usableAnchors(question, anchors).filter((a) => a.label);
  if (!labelled.length) return null;

  return (
    <p className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px] text-slate-blue">
      {labelled.map((anchor) => (
        <span key={anchor.token_id}>
          <span className="font-semibold text-ink">{anchor.text}</span>
          {' — '}
          {anchor.label}
        </span>
      ))}
    </p>
  );
}
