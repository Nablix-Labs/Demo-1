'use client';

/**
 * RescueNote — the bottom two rungs of the ladder, revealed a step at a time.
 *
 * A parallel example ("here is the same idea on an easier problem") or a
 * tutor-solved walkthrough ("let me do this one with you"). Both arrive whole
 * from the backend in `guided_rescue`, and both are shown one step at a time:
 * a worked solution dumped in full is an answer to read, whereas revealed step
 * by step it is a solution to follow.
 *
 * The final answer stays hidden until every step has been seen. Tutor-solved is
 * the only answer-reveal rung in the spec, and showing the answer above the
 * reasoning would make the reasoning optional.
 *
 * "Back to the question" is the return path the revised handoff asks for. It
 * only dismisses the card — the question, the canvas and the student's working
 * are all still underneath it, untouched. Whether the backend needs telling that
 * the student came back is Chirudeva's half of that line and is not decided
 * here; nothing in this component pretends to have told it.
 */

import { useEffect, useState } from 'react';
import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { isPhase3 } from '@/lib/phase3';
import { rescuePresentation, visibleSteps, fullyRevealed } from '@/lib/guidedRescue';
import { legacyRescueVisible } from '@/lib/rescueMode';
import StickyNote from '@/components/StickyNote';

const TITLE = {
  PARALLEL_EXAMPLE: 'A similar one',
  TUTOR_SOLVED: 'Let me show you',
} as const;

export default function RescueNote() {
  const rescue = useNumeraStore((s) => s.guidedRescue);
  const setRescue = useNumeraStore((s) => s.setGuidedRescue);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  /**
   * Whether this card is the one that may speak for the rescue rung.
   *
   * It is not, once a stepwise step exists — that is the contract the backend
   * is moving to, and this payload carries every step INCLUDING the answer. So
   * the two on screen together do not merely duplicate the panel: this one
   * hands over the answer the stepwise walkthrough is deliberately releasing a
   * step at a time. Two panels for one rescue is Chirudeva's 4 Sep report.
   */
  const mayRender = useNumeraStore(legacyRescueVisible);
  const view = rescuePresentation(rescue);

  // One step visible to begin with: the card opens showing the tutor starting
  // to work, not a finished solution the student is invited to read.
  const [revealed, setRevealed] = useState(1);
  // A new rescue starts from the top. Keyed on the identity of what is shown
  // rather than on the object, so a re-render cannot rewind a student's place.
  const key = `${view?.kind ?? ''}:${view?.problem ?? ''}:${view?.steps.length ?? 0}`;
  useEffect(() => setRevealed(1), [key]);

  if (!view) return null;
  if (!mayRender) return null;
  // Phase 3 is answered alone (spec §3.2) — the rescue rungs are support, and
  // support does not appear during an independent attempt. `mayRender` covers
  // this too; kept because it is this component's own rule and reads at the
  // point it applies.
  if (isPhase3(currentPhase)) return null;

  const shown = visibleSteps(view.steps, revealed);
  const done = fullyRevealed(view.steps, revealed);

  return (
    <aside className="relative max-w-[22rem]" aria-label={TITLE[view.kind]}>
      {/* Sky is the worked-example tone: "here is one done", modelled rather
          than asked. Both rungs are exactly that. */}
      <StickyNote tone="sky" label={TITLE[view.kind]}>
        {view.problem ? <span className="mb-2 block font-medium">{view.problem}</span> : null}

        <ol className="ml-4 list-decimal space-y-1">
          {shown.map((step, i) => (
            <li key={`${key}:${i}`}>{step}</li>
          ))}
        </ol>

        {/* The answer is the last thing to appear, and only once the steps that
            justify it have been read. */}
        {done && view.finalAnswer ? (
          <span className="mt-3 block font-medium">{view.finalAnswer}</span>
        ) : null}

        <div className="mt-3 flex items-center gap-3">
          {!done ? (
            <button
              onClick={() => setRevealed((n) => n + 1)}
              className="inline-flex items-center gap-1 rounded-md bg-white/70 px-2 py-1 text-sm font-medium hover:bg-white"
            >
              Next step <ChevronRight size={14} strokeWidth={2.2} />
            </button>
          ) : (
            <button
              onClick={() => setRescue(null)}
              className="inline-flex items-center gap-1 rounded-md bg-white/70 px-2 py-1 text-sm font-medium hover:bg-white"
            >
              <ArrowLeft size={14} strokeWidth={2.2} /> Back to the question
            </button>
          )}
          <span className="text-xs opacity-70">
            {Math.min(revealed, view.steps.length)} of {view.steps.length}
          </span>
        </div>
      </StickyNote>
    </aside>
  );
}
