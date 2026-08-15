'use client';

/**
 * HintNote — an authorised hint, shown as the tutor's paper.
 *
 * A hint used to reach the student only as a transcript bubble: no label, no
 * card, visually identical to the tutor talking, and gone entirely when the
 * panel was collapsed — a persisted preference, so once collapsed it stayed
 * that way across reloads. The hint was arriving, being logged and being
 * counted, and the student still never saw one (Sanya, 13 Aug 2026).
 *
 * Amber, like the cue, because both mean "notice something" and a student
 * should not have to learn two colours for one intent. The LABEL is what tells
 * them apart — see lib/cueLabel for why that distinction is drawn from what the
 * backend served rather than from what the client happens to hold.
 *
 * Still goes to the transcript as well. This is the thing you see; that is the
 * record of what was said.
 */

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import StickyNote from '@/components/StickyNote';

export default function HintNote() {
  const hint = useNumeraStore((s) => s.visibleHint);
  const setVisibleHint = useNumeraStore((s) => s.setVisibleHint);
  const currentPhase = useNumeraStore((s) => s.currentPhase);

  // Small entrance, matching VisualCue so two cards in the lane animate alike.
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!hint) {
      setShown(false);
      return;
    }
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, [hint]);

  if (!hint) return null;
  // Phase 3 is answered alone — no tutor support during an independent attempt
  // (Phase 3 spec §3.2). Suppressed at the render for the same reason the cue
  // is: a hint the backend still sends must not reach the screen.
  if (isPhase3(currentPhase)) return null;

  return (
    <div
      className="relative transition-all duration-300"
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(-6px)',
      }}
      aria-label="Hint"
    >
      <button
        onClick={() => setVisibleHint(null)}
        aria-label="Dismiss hint"
        className="absolute -right-1 -top-1 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-white/70 text-[#8A6407] shadow-sm hover:bg-white"
      >
        <X size={13} strokeWidth={2.2} />
      </button>

      <StickyNote tone="amber" label="Hint">{hint}</StickyNote>
    </div>
  );
}
