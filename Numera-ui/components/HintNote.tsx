'use client';

import { useId } from 'react';

/**
 * A hint, as a sticky note stuck to the canvas.
 *
 * It used to be a white rounded card with the same visual weight as the toolbar
 * and the status pills, so it read as app chrome. A hint is not chrome: it is
 * something the tutor has left for the student, and it should look placed
 * rather than rendered.
 *
 * The silhouette is an SVG clip path rather than a rectangle — real paper does
 * not have four straight edges, and the slight lift along the bottom is what
 * stops it reading as a coloured div. Written in the same hand the tutor writes
 * on the canvas with, because it is the same tutor.
 */

/** Paper edge: square top, a shallow curl lifting along the bottom. */
const PAPER_PATH =
  'M 0 0 Q 0 0.69, 0.03 0.96 0.03 0.96, 1 0.96 Q 0.96 0.69, 0.96 0 0.96 0, 0 0';

export default function HintNote({
  children,
  label = 'Gentle hint',
  className = '',
}: {
  children: React.ReactNode;
  label?: string;
  className?: string;
}) {
  // Every note needs its own clip id — a shared literal id would be duplicated
  // in the document the moment two hints are on screen at once.
  const clipId = useId().replace(/:/g, '');

  return (
    <div className={`w-[248px] ${className}`}>
      <div className="relative">
        {/* Shadow sits behind and slightly below the paper: the note is resting
            on the canvas, not floating above it. Inset from the edges so it
            never shows past the curl. */}
        <span
          aria-hidden="true"
          className="absolute left-[6px] top-[16%] h-[76%] w-[92%]"
          style={{
            background: 'rgba(92, 66, 12, .16)',
            boxShadow: '-2px 3px 16px 0 rgba(92, 66, 12, .38)',
          }}
        />

        <svg width="0" height="0" aria-hidden="true" style={{ position: 'absolute' }}>
          <defs>
            <clipPath id={clipId} clipPathUnits="objectBoundingBox">
              <path d={PAPER_PATH} strokeLinejoin="round" strokeLinecap="square" />
            </clipPath>
          </defs>
        </svg>

        <div
          role="note"
          className="relative flex min-h-[214px] flex-col justify-center px-6 py-7"
          style={{
            // Warm amber stock, matching the hint accent the session trail
            // already uses, so the two read as the same thing in two places.
            background:
              'linear-gradient(180deg, #FFF3CE 0%, #FFF0C2 12%, #FCE49B 75%, #FFF1C6 100%)',
            clipPath: `url(#${clipId})`,
          }}
        >
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[#8A6407]">
            {label}
          </div>
          <p
            className="text-[19px] leading-[1.35] text-[#3A2E10]"
            style={{ fontFamily: 'var(--font-tutor-hand), cursive' }}
          >
            {children}
          </p>
        </div>
      </div>
    </div>
  );
}
