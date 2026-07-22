'use client';

/**
 * useTutorReveal — drives the "handwriting" reveal of tutor canvas marks.
 *
 * The backend delivers a batch of tutor elements all at once; rendering them
 * instantly reads as mechanical. This store sequences them one at a time and
 * exposes a per-element `progress` (0→1) that the tutor layers use to draw each
 * mark as if it were being written — text typed out, strokes drawn end-to-end,
 * outlines traced around.
 *
 * Kept SEPARATE from useNumeraStore on purpose: progress updates every animation
 * frame, and only the tutor layers subscribe here — putting it in the main store
 * would re-render the canvas, toolbar and panel ~60×/sec (same reason
 * useMicLevel is its own store).
 */

import { create } from 'zustand';
import { useEffect } from 'react';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';

const GAP_MS = 90; // pause between finishing one mark and starting the next

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' &&
    Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/**
 * Ease the raw 0→1 progress so marks accelerate and settle like a hand, instead
 * of tracing at a constant machine rate. easeInOutCubic — gentle start, smooth
 * finish — is what makes the writing read as deliberate rather than mechanical.
 */
function ease(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * How long a single mark takes to "write", scaled by how much there is to draw.
 * Paced for a calm, deliberate hand — slow enough to read as writing, not a pop.
 */
function durationFor(el: TutorElement): number {
  switch (el.kind) {
    case 'text':      return Math.max(420, (el.text?.length ?? 0) * 55);
    case 'math':      return Math.max(460, (el.tex ?? el.text ?? '').length * 46);
    case 'line':      return 380;
    case 'arrow':     return 460;
    case 'ellipse':   return 720;
    case 'rect':      return 640;
    case 'freehand':  return Math.max(380, ((el.points?.length ?? 0) / 2) * 20);
    case 'highlight': return Math.max(300, ((el.points?.length ?? 0) / 2) * 15);
    default:          return 380;
  }
}

interface RevealState {
  progress: Record<string, number>;
  /** Reconcile the reveal queue with the current tutor elements. */
  sync: (elements: TutorElement[]) => void;
}

export const useTutorReveal = create<RevealState>((set, get) => {
  let queue: { id: string; duration: number }[] = [];
  let running = false;

  const step = () => {
    const job = queue[0];
    if (!job) { running = false; return; }
    const start = performance.now();
    const tick = () => {
      // The element may have been cleared mid-write (replace/clear) — bail.
      if (get().progress[job.id] === undefined) { queue.shift(); step(); return; }
      const raw = Math.min(1, (performance.now() - start) / job.duration);
      set((s) => ({ progress: { ...s.progress, [job.id]: ease(raw) } }));
      if (raw < 1) { requestAnimationFrame(tick); return; }
      queue.shift();
      setTimeout(() => requestAnimationFrame(step), GAP_MS);
    };
    requestAnimationFrame(tick);
  };

  return {
    progress: {},

    sync: (elements) => {
      const ids = new Set(elements.map((e) => e.id));
      const cur = get().progress;

      // Drop progress for elements that no longer exist (a `replace` batch, or
      // clearTutorMarks). Also drop them from the queue.
      let next = cur;
      let changed = false;
      for (const id of Object.keys(cur)) {
        if (!ids.has(id)) {
          if (!changed) { next = { ...cur }; changed = true; }
          delete next[id];
        }
      }
      queue = queue.filter((j) => ids.has(j.id));

      // Reduced motion: show everything at once, no animation.
      if (prefersReducedMotion()) {
        const full: Record<string, number> = {};
        for (const e of elements) full[e.id] = 1;
        queue = [];
        running = false;
        set({ progress: full });
        return;
      }

      // Enqueue any newly-seen elements, in delivery order, starting hidden.
      const queued = new Set(queue.map((j) => j.id));
      const additions: Record<string, number> = {};
      for (const el of elements) {
        if (next[el.id] === undefined && !queued.has(el.id)) {
          queue.push({ id: el.id, duration: durationFor(el) });
          additions[el.id] = 0;
        }
      }

      if (changed || Object.keys(additions).length) {
        set({ progress: { ...next, ...additions } });
      }
      if (!running && queue.length) { running = true; step(); }
    },
  };
});

/** Mount once (in the canvas): feeds tutor element changes into the sequencer. */
export function useTutorRevealSync(): void {
  const tutorElements = useNumeraStore((s) => s.tutorElements);
  const sync = useTutorReveal((s) => s.sync);
  useEffect(() => { sync(tutorElements); }, [tutorElements, sync]);
}
