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

import type { CSSProperties, ReactNode } from 'react';
import { DrawablyCircle, DrawablyHighlight } from 'drawably/react';
import 'drawably/style.css';
import { anchorSegments, usableAnchors, type QuestionAnchor } from '@/lib/questionAnchors';
import { TEACHING_COLORS, type CanvasTeachingColor, type TeachingTokenMark } from '@/lib/canvasTeachingPlan';
import { useNumeraStore } from '@/store/useNumeraStore';

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

/** A teaching colour at the given alpha (0–1), as 8-digit hex. */
function tint(hex: string, alpha: number): string {
  return `${hex}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`;
}

/**
 * The canvas teaching plan's marks on one token, wrapped round it innermost
 * first: highlight, then box, then circle, then a check badge after it.
 *
 * Drawn here rather than on the canvas for the reason the anchors are — the
 * question is HTML that rewraps, and only this renderer knows where the token
 * went.
 *
 * Styling rules, after the first pass read as scribble (Manav, 26 Sep):
 *   - every mark gives the glyph room — a circle hugging a single digit is a
 *     vertical sliver that cuts through it;
 *   - the text itself never fades or moves. A PULSE is a ring that ripples
 *     OUT from the mark (`teaching-pulse`), because the student is reading the
 *     very word being pointed at;
 *   - marks arrive with a short settle (`teaching-in`), off under reduced motion.
 */
function withTeachingMarks(
  tokenId: string,
  node: ReactNode,
  marks: TeachingTokenMark[],
  linkColor: CanvasTeachingColor | null,
): ReactNode {
  const mine = marks.filter((m) => m.tokenId === tokenId);
  if (!mine.length && !linkColor) return node;
  const pulse = mine.find((m) => m.pulse);
  const find = (style: TeachingTokenMark['style']) => mine.filter((m) => m.style === style).at(-1);

  let out = node;
  const highlight = find('highlight');
  if (highlight) {
    const ink = TEACHING_COLORS[highlight.color];
    out = (
      <span className="teaching-in rounded-[5px] px-[4px] -mx-[1px]" style={{ background: tint(ink, 0.28), boxShadow: `inset 0 -2px 0 ${tint(ink, 0.55)}` }}>
        {out}
      </span>
    );
  }
  // CONNECT: the linked tokens share an underline in the link's colour, so the
  // relationship reads even where an arrow would be too short to see. Not on a
  // boxed or circled token — the enclosure already groups it, and an underline
  // inside one is clutter.
  if (linkColor && !find('box') && !find('circle')) {
    out = (
      <span className="teaching-in" style={{ textDecoration: `underline 2px ${TEACHING_COLORS[linkColor]}`, textUnderlineOffset: 5 }}>
        {out}
      </span>
    );
  }
  const box = find('box');
  if (box) {
    const ink = TEACHING_COLORS[box.color];
    out = (
      <span className="teaching-in inline-block rounded-md px-[6px] leading-[1.25]" style={{ background: tint(ink, 0.08), boxShadow: `inset 0 0 0 1.5px ${tint(ink, 0.85)}` }}>
        {out}
      </span>
    );
  }
  const circle = find('circle');
  if (circle) {
    out = (
      <DrawablyCircle className="teaching-in" boil={0} width={2} seed={seedFor(circle.id)} stroke={TEACHING_COLORS[circle.color]}>
        <span className="inline-block px-[9px] py-[2px]">{out}</span>
      </DrawablyCircle>
    );
  }
  const check = find('check');
  return (
    <span
      className={`relative inline-block ${pulse ? 'teaching-pulse' : ''}`}
      style={pulse ? { '--teaching-pulse': tint(TEACHING_COLORS[pulse.color], 0.45) } as CSSProperties : undefined}
    >
      {out}
      {check && (
        <span
          aria-hidden="true"
          className="teaching-in ml-1 inline-flex h-[15px] w-[15px] items-center justify-center rounded-full align-middle text-[10px] font-bold leading-none text-white"
          style={{ background: TEACHING_COLORS[check.color] }}
        >
          ✓
        </span>
      )}
    </span>
  );
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
  const teachingMarks = useNumeraStore((s) => s.teachingMarks);
  const teachingConnectors = useNumeraStore((s) => s.teachingConnectors);
  const linkColor = (tokenId: string) =>
    teachingConnectors.find((c) => c.fromTokenId === tokenId || c.toTokenId === tokenId)?.color ?? null;

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
          // `data-qtoken` is how a teaching-plan arrow finds this token
          // (TeachingConnectors). Every anchored token carries it.
          <span key={i} data-qtoken={segment.anchor.token_id}>
            {withTeachingMarks(segment.anchor.token_id, segment.text, teachingMarks, linkColor(segment.anchor.token_id))}
          </span>
        ) : (
          <span key={i} data-qtoken={segment.anchor.token_id} className="relative inline whitespace-nowrap">
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
            {withTeachingMarks(segment.anchor.token_id, (
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
            ), teachingMarks, linkColor(segment.anchor.token_id))}
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
