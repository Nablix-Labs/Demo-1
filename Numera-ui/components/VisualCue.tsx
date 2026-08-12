'use client';

/**
 * VisualCue — the instructional cue card shown when the AI Engine flags a
 * student mistake.
 *
 * The backend sends a `visual_cue` object (show + cue_type + description); the
 * store holds `visualCueVisible` / `visualCueType` / `visualCueDescription`.
 * This picks the matching card from the static library (lib/visualCueCards) and
 * renders title, worked example, steps and caption, with the backend
 * `description` layered on as an extra guidance note. The card never reveals the
 * final answer — it nudges the next step. Kept in the top-left corner so it
 * supports the student's working without covering it or the practice button.
 */

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import { resolveCueCard } from '@/lib/visualCueCards';
import { cn } from '@/lib/cn';
import StickyNote from '@/components/StickyNote';

export default function VisualCue() {
  const visible = useNumeraStore((s) => s.visualCueVisible);
  const setVisible = useNumeraStore((s) => s.setVisualCueVisible);
  const cueType = useNumeraStore((s) => s.visualCueType);
  const description = useNumeraStore((s) => s.visualCueDescription);
  const assetUrl = useNumeraStore((s) => s.visualCueAssetUrl);
  const panelSide = useNumeraStore((s) => s.panelSide);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const card = resolveCueCard(cueType);
  // A note with no authored card is the tutor's own guidance text — the hint
  // rung of the support ladder, not a cue card. Titling it "Visual cue" told
  // the student a hint was something else (Manjusha, 10 Aug). The card's own
  // title stands when there is one.
  const label = card?.title ?? 'Hint';

  // Small entrance (fade + rise) without depending on a motion library.
  const [shown, setShown] = useState(false);
  // Reset per cue: a failure on one image must not suppress the next one.
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => setImageFailed(false), [assetUrl]);
  useEffect(() => {
    if (visible) {
      const id = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(id);
    }
    setShown(false);
  }, [visible]);

  // Nothing authored and nothing to say — show nothing, rather than a card
  // about an equation the student isn't working on.
  if (!visible || (!card && !description)) return null;
  // Phase 3 is answered alone: no visual cues during an independent attempt
  // (Phase 3 spec §3.2). Suppressed at the render rather than at the source so
  // a cue the backend still sends cannot leak onto the screen.
  if (isPhase3(currentPhase)) return null;

  return (
    <aside
      // Right side (matches the design mockup: canvas left, cue right). Sits
      // below the "Explain it back" chrome so it stacks under it, not over it.
      className={cn(
        'fixed top-[84px] z-30 transition-all duration-300',
        panelSide === 'right' ? 'left-4' : 'right-4',
      )}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(-6px)',
      }}
      aria-label={label}
    >
      <div className="relative">
        <button
          onClick={() => setVisible(false)}
          aria-label={`Dismiss ${label.toLowerCase()}`}
          className="absolute -right-1 -top-1 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-white/70 text-[#8A6407] shadow-sm hover:bg-white"
        >
          <X size={13} strokeWidth={2.2} />
        </button>

        {/* Amber is the cue tone: "notice something", the default nudge. The
            steps are the tutor's words about the example, so they sit under it
            as the annotation rather than beside it. */}
        <StickyNote tone="amber" label={label} lines={card ? [card.example] : undefined}>
          {card?.caption}
          {description ? <span className="mt-2 block">{description}</span> : null}
          {/* The picture is ADDITIVE — the text card above is the cue itself.
              A missing, malformed or unreachable image must never cost the
              student the cue, so a load failure just hides the <img> (Sanya,
              12 Aug 2026: "do not break the existing text-card cue if the
              image is unavailable"). */}
          {assetUrl && !imageFailed ? (
            <img
              src={assetUrl}
              alt={description ?? 'Visual cue'}
              onError={() => setImageFailed(true)}
              className="mt-3 block w-full rounded-md border border-muted-gray bg-white object-contain"
            />
          ) : null}
        </StickyNote>
      </div>
    </aside>
  );
}
