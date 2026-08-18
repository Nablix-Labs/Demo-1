'use client';

import { useId } from 'react';

/**
 * StickyNote — the tutor's paper on the canvas.
 *
 * Four tones, each with a job, so a student learns what a colour means before
 * they read it:
 *
 *   amber  visual cue      "notice something"      — the default nudge
 *   sky    worked example  "here is one done"      — modelled, not asked
 *   mint   confirmed       "you already got this"  — never corrective
 *   rose   scaffold step   "one guided question"   — expects an answer
 *
 * The silhouette is an SVG clip path rather than a rectangle: real paper does
 * not have four straight edges, and the curl along the bottom is what stops it
 * reading as a coloured div.
 *
 * Layout is the part worth being careful about. The maths and the annotation
 * are separate blocks, stacked, never side by side — set beside each other they
 * collide the moment either one is longer than the mock, which is exactly how
 * "3 + 5The start changes" happens. Maths gets a serif and room to breathe
 * because it is the thing being looked at; the annotation is handwriting
 * underneath, because it is the tutor talking about it.
 */

/** Square top, a shallow curl lifting along the bottom edge. */
const PAPER_PATH =
  'M 0 0 Q 0 0.69, 0.03 0.96 0.03 0.96, 1 0.96 Q 0.96 0.69, 0.96 0 0.96 0, 0 0';

export type NoteTone = 'amber' | 'sky' | 'mint' | 'rose';

const TONES: Record<NoteTone, { paper: string; label: string; ink: string; rule: string }> = {
  amber: {
    paper: 'linear-gradient(175deg, #FBE9A0 0%, #F8DE85 55%, #F3D269 100%)',
    label: '#8A6407',
    ink: '#3A2E10',
    rule: 'rgba(138,100,7,.22)',
  },
  sky: {
    paper: 'linear-gradient(175deg, #BEDFF2 0%, #A9D3EC 55%, #93C6E4 100%)',
    label: '#1E5C82',
    ink: '#14314A',
    rule: 'rgba(30,92,130,.22)',
  },
  mint: {
    paper: 'linear-gradient(175deg, #BFE3BC 0%, #A9DAA6 55%, #93CE90 100%)',
    label: '#2E6B33',
    ink: '#1B3A1E',
    rule: 'rgba(46,107,51,.22)',
  },
  rose: {
    paper: 'linear-gradient(175deg, #F6CBD2 0%, #F0B7C0 55%, #E9A3AF 100%)',
    label: '#8C3A4B',
    ink: '#43202A',
    rule: 'rgba(140,58,75,.22)',
  },
};

export default function StickyNote({
  tone = 'amber',
  label,
  lines,
  children,
  className = '',
}: {
  tone?: NoteTone;
  /** Small caps across the top — what kind of note this is. */
  label: string;
  /** The maths being pointed at, one string per line. Optional. */
  lines?: string[];
  /** The tutor's words about it. Optional. */
  children?: React.ReactNode;
  className?: string;
}) {
  // Each note needs its own clip id: a shared literal would be a duplicate DOM
  // id the moment two notes are on screen together.
  const clipId = useId().replace(/:/g, '');
  const t = TONES[tone];

  return (
    <div className={`w-[264px] ${className}`}>
      <div className="relative">
        {/* The note rests on the surface — shadow sits under and slightly left,
            inset so it never shows past the curl. */}
        <span
          aria-hidden="true"
          className="absolute left-[6px] top-[18%] h-[74%] w-[92%]"
          style={{ background: 'rgba(72,52,10,.14)', boxShadow: '-2px 3px 16px 0 rgba(72,52,10,.34)' }}
        />

        <svg width="0" height="0" aria-hidden="true" style={{ position: 'absolute' }}>
          <defs>
            <clipPath id={clipId} clipPathUnits="objectBoundingBox">
              <path d={PAPER_PATH} />
            </clipPath>
          </defs>
        </svg>

        <div
          role="note"
          className="relative flex min-h-[196px] flex-col px-6 pb-9 pt-6"
          style={{ background: t.paper, clipPath: `url(#${clipId})` }}
        >
          <div
            className="text-[9.5px] font-bold uppercase leading-none tracking-[0.18em]"
            style={{ color: t.label }}
          >
            {label}
          </div>

          {lines && lines.length > 0 && (
            <div className="mt-4 space-y-1.5">
              {lines.map((line, i) => (
                <div
                  key={i}
                  className="font-serif text-[26px] leading-none tabular-nums"
                  style={{ color: t.ink, letterSpacing: '0.01em' }}
                >
                  {line}
                </div>
              ))}
            </div>
          )}

          {children && (
            <>
              {lines && lines.length > 0 && (
                <div className="mt-4 h-px w-10" style={{ background: t.rule }} aria-hidden="true" />
              )}
              {/* A div, not a <p>: the annotation slot holds whatever the note
                  is about, and the rescue note's content is a numbered list of
                  worked steps with a control under it. An <ol> or a <div> inside
                  a <p> is invalid HTML — the browser closes the paragraph early,
                  which React reports as a hydration error and which reorders the
                  card on screen. Identical visually: Tailwind's preflight zeroes
                  the paragraph margin this was relying on not having. */}
              <div
                className={`${lines && lines.length ? 'mt-3' : 'mt-3.5'} text-[17px] leading-[1.4]`}
                style={{ color: t.ink, fontFamily: 'var(--font-tutor-hand), cursive' }}
              >
                {children}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
