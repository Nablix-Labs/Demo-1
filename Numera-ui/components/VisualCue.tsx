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
import { Lightbulb, Info, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { resolveCueCard } from '@/lib/visualCueCards';

export default function VisualCue() {
  const visible = useNumeraStore((s) => s.visualCueVisible);
  const setVisible = useNumeraStore((s) => s.setVisualCueVisible);
  const cueType = useNumeraStore((s) => s.visualCueType);
  const description = useNumeraStore((s) => s.visualCueDescription);
  const card = resolveCueCard(cueType);

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
      // Right side (matches the design mockup: canvas left, cue right). Sits
      // below the "Explain it back" chrome so it stacks under it, not over it.
      className="lg-glass fixed top-[84px] right-4 z-30 w-72 rounded-card overflow-hidden transition-all duration-300"
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? 'translateY(0)' : 'translateY(-6px)',
      }}
      aria-label={`Visual cue: ${card.title}`}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-muted-gray bg-reading-surface">
        <div className="flex items-center gap-1.5 text-[12px] font-semibold text-slate-blue">
          <Lightbulb size={14} strokeWidth={1.9} /> Visual cue: {card.title}
        </div>
        <button
          onClick={() => setVisible(false)}
          aria-label="Dismiss visual cue"
          className="w-5 h-5 rounded flex items-center justify-center text-slate-blue hover:bg-muted-gray/50 hover:text-ink transition-colors"
        >
          <X size={14} strokeWidth={2} />
        </button>
      </div>

      <div className="p-3 space-y-3">
        {/* Worked example — the equation this card is guiding, not the answer. */}
        <div className="rounded-lg bg-reading-surface border border-muted-gray py-3 px-2 text-center">
          <span className="text-[16px] font-semibold text-ink" style={{ fontFamily: 'Georgia, "Times New Roman", serif' }}>
            {card.example}
          </span>
        </div>

        {/* Steps toward the next move. */}
        <ol className="space-y-1.5">
          {card.steps.map((step, i) => (
            <li key={i} className="flex gap-2 text-[12px] text-ink leading-snug">
              <span className="flex-shrink-0 w-4 h-4 mt-[1px] rounded-full bg-slate-blue/15 text-slate-blue text-[10px] font-bold flex items-center justify-center">
                {i + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>

        <p className="text-[12px] text-ink leading-snug font-medium">{card.caption}</p>

        {/* Backend's instructional description, when provided. */}
        {description && (
          <div className="flex gap-1.5 rounded-lg bg-slate-blue/[0.08] border border-slate-blue/20 px-2.5 py-2">
            <Info size={13} strokeWidth={2} className="flex-shrink-0 mt-[1px] text-slate-blue" />
            <p className="text-[11px] text-slate-blue leading-snug">{description}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
