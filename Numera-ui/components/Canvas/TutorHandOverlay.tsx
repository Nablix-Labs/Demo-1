'use client';

/**
 * TutorHandOverlay — a writing hand that rides the tip of whatever the tutor is
 * currently drawing, in the whiteboard-animation style.
 *
 * The hand never rotates. It sits at a fixed angle and only translates, which is
 * what makes the effect read as a person writing rather than a sprite being
 * dragged around; rotating it to follow stroke direction is the thing that looks
 * wrong. It enters from the lower-right, so it covers the area that has not been
 * written yet and never the working the student is meant to read.
 *
 * State comes entirely from the reveal progress map, so useTutorReveal needs no
 * changes: exactly one mark is ever mid-write, which makes the three cases
 * unambiguous —
 *   0 < p < 1 for some element  → that element is being written; sit on its tip
 *   none active, some at p = 0  → between marks; glide to the next start point
 *   all at p = 1                → the batch is done; lift away
 *
 * The transform is written imperatively to a ref rather than through React
 * state: this moves every animation frame, and re-rendering the tree 60×/sec is
 * exactly what putting the reveal in its own store was meant to avoid.
 */

import { useEffect, useRef } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useTutorReveal } from '@/store/useTutorReveal';
import { tipFor } from '@/lib/tutorTip';

/** Measured from the asset itself — the nib, as a fraction of the image box. */
const HAND = {
  src: '/tutor/hand-write.webp',
  tip: [0.1389, 0.0944] as const,
  /** Of the live canvas height. Large enough that the forearm reaches the edge. */
  heightRatio: 0.85,
};

const GLIDE_MS = 90; // matches GAP_MS in useTutorReveal

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' &&
    Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

export default function TutorHandOverlay({ width, height }: { width: number; height: number }) {
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    // With reduced motion the store completes every mark instantly, so nothing
    // is ever mid-write and a hand would only ever flicker. Stay out entirely.
    if (prefersReducedMotion()) return;

    const size = height * HAND.heightRatio;
    const anchorX = HAND.tip[0] * size;
    const anchorY = HAND.tip[1] * size;

    const paint = () => {
      const node = ref.current;
      if (!node) return;

      const elements = useNumeraStore.getState().tutorElements;
      const progress = useTutorReveal.getState().progress;

      let active: (typeof elements)[number] | undefined;
      let activeP = 0;
      let next: (typeof elements)[number] | undefined;

      for (const el of elements) {
        const p = progress[el.id];
        if (p === undefined) continue;
        if (p > 0 && p < 1) { active = el; activeP = p; break; }
        if (p === 0 && !next) next = el; // first mark not yet started
      }

      const target = active
        ? tipFor(active, activeP, width, height)
        : next
          ? tipFor(next, 0, width, height)
          : null;

      if (!target) {
        node.style.opacity = '0';
        return;
      }

      // Follow the tip exactly while writing; ease only across the gap, so the
      // hand travels to the next mark instead of cutting to it.
      node.style.transition = active
        ? 'opacity 160ms ease'
        : `transform ${GLIDE_MS}ms linear, opacity 160ms ease`;
      node.style.transform = `translate(${target.x - anchorX}px, ${target.y - anchorY}px)`;
      node.style.opacity = '1';
    };

    // Repaint on every progress tick. Subscribing to the store rather than
    // driving our own rAF means the hand cannot drift out of step with the ink.
    const unsub = useTutorReveal.subscribe(paint);
    paint();
    return unsub;
  }, [width, height]);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={ref}
        src={HAND.src}
        alt=""
        draggable={false}
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          height: height * HAND.heightRatio,
          width: height * HAND.heightRatio,
          transformOrigin: '0 0',
          opacity: 0,
          willChange: 'transform',
        }}
      />
    </div>
  );
}
