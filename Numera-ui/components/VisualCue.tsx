'use client';

/**
 * VisualCue — a supporting picture shown during guided practice.
 *
 * Appears on the canvas when the tutor decides a visual would help (backend
 * `show_visual_cue` → store `visualCueVisible`). Renders the current topic's
 * concept illustration + a one-line caption, and can be dismissed. Kept small
 * and to a corner so it supports the student's working without covering it.
 */

import { useEffect, useState } from 'react';
import { Image as ImageIcon, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useFlowNav } from '@/lib/useFlowNav';
import { demoFor } from '@/lib/demoContent';
import ConceptArt from './ConceptArt';

export default function VisualCue() {
  const visible = useNumeraStore((s) => s.visualCueVisible);
  const setVisible = useNumeraStore((s) => s.setVisualCueVisible);
  const { currentTopicId } = useFlowNav();
  const cue = demoFor(currentTopicId).visualCue;

  // Small entrance (fade + rise) without depending on a motion library.
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (visible) {
      const id = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(id);
    }
    setShown(false);
  }, [visible]);

  if (!visible) return null;

  return (
    <aside
      // Top-left corner: keeps clear of the "Finish lesson → Practice" button,
      // which is pinned top-right (they used to collide in that corner).
      className="lg-glass fixed top-4 left-4 z-30 w-64 rounded-card overflow-hidden transition-all duration-300"
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(-6px)',
      }}
      aria-label="Visual cue"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-muted-gray bg-reading-surface">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold tracking-widest uppercase text-slate-blue">
          <ImageIcon size={13} strokeWidth={1.9} /> Visual cue
        </div>
        <button
          onClick={() => setVisible(false)}
          aria-label="Dismiss visual cue"
          className="w-5 h-5 rounded flex items-center justify-center text-slate-blue hover:bg-muted-gray/50 hover:text-ink transition-colors"
        >
          <X size={14} strokeWidth={2} />
        </button>
      </div>

      <div className="p-3">
        <div className="rounded-lg bg-reading-surface border border-muted-gray p-2">
          <ConceptArt name={cue.art} className="w-full h-auto" />
        </div>
        <p className="text-[12px] text-ink leading-snug mt-2.5">{cue.caption}</p>
      </div>
    </aside>
  );
}
