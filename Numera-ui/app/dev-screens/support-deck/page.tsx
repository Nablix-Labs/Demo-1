'use client';

/**
 * /dev-screens/support-deck — the Phase 2 support deck on fixtures.
 *
 * Manjusha asked for this reorganisation (5 Sep) and is the one who has to say
 * whether it reads better. Driving a real guided session to four rungs takes a
 * backend, a live VM and a student who keeps getting things wrong; this takes a
 * click. Under /dev-screens, which AppFrame already treats as pre-auth and
 * full-bleed, so it needs no login and no routing changes.
 *
 * It writes the real store and renders the real components — so what is on this
 * page is what a student sees, not a mock of it. The "before" toggle is the
 * point of comparison: it stacks every rung the way the lane used to, which is
 * the screenshot she sent.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useNumeraStore } from '@/store/useNumeraStore';
import { deckRungs, visibleRung, collapsedRungs } from '@/lib/supportDeck';
import SupportDeck from '@/components/SupportDeck';
import ScaffoldPanel from '@/components/ScaffoldPanel';
import WriteNote from '@/components/WriteNote';
import HintNote from '@/components/HintNote';
import VisualCue from '@/components/VisualCue';
import RescueSteps from '@/components/RescueSteps';

const HINT = 'What happens to the +5 each time?';
const CUE = 'One rule, many cases — look at what stays the same.';
const WRITE = 'Write the next line of your working.';
const SCAFFOLD = {
  scaffoldId: 'SC-1',
  currentStepId: 'ST-1',
  stepNumber: 1,
  stepText: 'What changes?',
  stepVoice: null,
  totalSteps: 4,
};

type Toggle = 'hint' | 'cue' | 'rescue' | 'write' | 'scaffold';

export default function SupportDeckDevScreen() {
  const [on, setOn] = useState<Record<Toggle, boolean>>({
    hint: true, cue: true, rescue: false, write: false, scaffold: true,
  });
  const [before, setBefore] = useState(false);

  // Written straight into the store so the components below are the real ones
  // reading their real fields — a fixture that bypassed the store would prove
  // nothing about what a student sees.
  useEffect(() => {
    const s = useNumeraStore.getState();
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-DEV-1',
      supportDeck: [],
      openedRung: null,
      deckCollapsed: false,
      visibleHint: null,
      visualCueVisible: false,
      visualCueId: null,
      visualCueDescription: null,
      visualCueAssetUrl: null,
      rescueSteps: [],
      guidedRescue: null,
      writeInstruction: on.write ? WRITE : null,
      activeScaffold: on.scaffold ? SCAFFOLD : null,
    });
    // Through the setters, in ladder order, so the deck records the arrivals
    // exactly as a real session would.
    if (on.hint) s.setVisibleHint(HINT);
    if (on.cue) s.setVisualCue({ show: true, cueId: 'CUE-DEV', description: CUE });
    if (on.rescue) {
      useNumeraStore.setState({
        rescueSteps: [{
          actionId: 'A1', rescueId: 'R1', mode: 'TUTOR_SOLVED', stepIndex: 4,
          totalSteps: 4, text: 'Replace the changing starting number with n and write n + 5.',
          anchorId: 'T1', returnTargetObjectId: null,
        }] as never,
        supportDeck: [...useNumeraStore.getState().supportDeck, 'TUTOR_SOLVED'],
      });
    }
  }, [on]);

  const rungs = useNumeraStore(deckRungs);
  const showing = useNumeraStore(visibleRung);
  const earlier = useNumeraStore(collapsedRungs);
  const flip = (k: Toggle) => setOn((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div className="min-h-full bg-reading-surface p-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link href="/" className="text-[12px] font-semibold text-learning-blue hover:underline">← Back</Link>
        <span className="text-[12px] text-slate-blue">Phase 2 support deck (fixture)</span>
        {(['hint', 'cue', 'rescue', 'write', 'scaffold'] as Toggle[]).map((k) => (
          <button
            key={k}
            onClick={() => flip(k)}
            className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${
              on[k] ? 'bg-learning-blue text-white' : 'lg-chip text-ink/70'
            }`}
          >
            {k}
          </button>
        ))}
        <button
          onClick={() => setBefore((b) => !b)}
          className={`rounded-full px-3 py-1.5 text-[12px] font-semibold ${
            before ? 'bg-slate-blue text-white' : 'lg-chip text-ink/70'
          }`}
        >
          {before ? 'showing BEFORE' : 'showing AFTER'}
        </button>
      </div>

      <div className="flex gap-6">
        {/* Stands in for the canvas: the question and the guided step sit here,
            which is where they are on the real screen. */}
        <div className="relative min-h-[520px] flex-1 rounded-xl border border-muted-gray bg-white p-6">
          <p className="mb-3 font-serif text-[19px] text-ink">
            5 + 2, 11 + 2, 18 + 2. Use n for the changing starting number.
          </p>
          {on.scaffold && !(before && on.rescue) && <ScaffoldPanel scaffold={SCAFFOLD} />}
          <div className="mt-10 font-serif text-[44px] text-ink/80">n + 5</div>
        </div>

        <div className="w-[300px] shrink-0">
          {before ? (
            // What the lane used to do: every rung, stacked, all at once.
            <div className="flex flex-col gap-3">
              {on.write && <WriteNote />}
              {!on.rescue && <><HintNote /><VisualCue /></>}
              {on.rescue && <RescueSteps />}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {on.write && <WriteNote />}
              <SupportDeck />
            </div>
          )}
        </div>
      </div>

      <div className="mt-5 rounded-lg border border-muted-gray bg-white px-4 py-3 text-[12px] text-slate-blue">
        <span className="font-semibold text-ink">deck</span>{' '}
        [{rungs.join(', ') || '—'}] &nbsp;·&nbsp;
        <span className="font-semibold text-ink">showing</span> {showing ?? '—'} &nbsp;·&nbsp;
        <span className="font-semibold text-ink">chips</span> [{earlier.join(', ') || '—'}]
      </div>
    </div>
  );
}
