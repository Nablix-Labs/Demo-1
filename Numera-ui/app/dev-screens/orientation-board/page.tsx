'use client';

/**
 * /dev-screens/orientation-board — the Phase 1 worked example on real content.
 *
 * `alg-ori-02.json` is ALG-ORI-02's "Decoding Compact Algebraic Notation" as the
 * Student Model serves it: eight one-step worked examples sharing a title
 * (copied from the authoring v3 sample). The toggle shows the board before and
 * after lib/orientationBoard.ts merges them — one line at a time that wipes
 * itself, versus one board that builds down the page.
 *
 * A live check needs a student who has not passed orientation, which the test
 * accounts all have; this needs nothing.
 */

import { useState } from 'react';
import Link from 'next/link';
import { WorkedExampleCanvas } from '@/app/orientation/OrientationClient';
import { mergeWorkedExampleRuns } from '@/lib/orientationBoard';
import type { SchemaOrientationItem } from '@/lib/api';
import fixture from './alg-ori-02.json';

const ITEMS = fixture as SchemaOrientationItem[];
const MERGED = mergeWorkedExampleRuns(ITEMS);

export default function OrientationBoardDevScreen() {
  const [merged, setMerged] = useState(true);
  const [index, setIndex] = useState(0);
  const [run, setRun] = useState(0);
  const items = merged ? MERGED : ITEMS;
  const item = items[Math.min(index, items.length - 1)];

  const show = (m: boolean) => { setMerged(m); setIndex(0); setRun((r) => r + 1); };

  return (
    // `w-full`: the focus-route frame otherwise sizes the page to its content,
    // which left the board in the left half with the backdrop showing (4 Oct).
    <main className="min-h-screen w-full bg-white px-6 py-5">
      <div className="mx-auto max-w-[1000px]">
        <div className="flex flex-wrap items-center gap-3 text-[12.5px] mb-4">
          <Link href="/dev-screens" className="text-slate-blue hover:text-ink">← Dev screens</Link>
          <span className="text-slate-blue">Phase 1 worked example · ALG-ORI-02 (8 one-step examples)</span>
          <button onClick={() => show(false)} className={`rounded-full px-3 py-1 border ${!merged ? 'bg-focus-navy text-white' : 'text-ink'}`}>Before</button>
          <button onClick={() => show(true)} className={`rounded-full px-3 py-1 border ${merged ? 'bg-focus-navy text-white' : 'text-ink'}`}>After</button>
          {!merged && <span className="text-slate-blue">example {index + 1} of {items.length}</span>}
        </div>
        {item?.worked_example && (
          <WorkedExampleCanvas
            key={`${merged}-${index}-${run}`}
            example={item.worked_example}
            closingMessage={null}
            onFinished={() => { if (index < items.length - 1) setIndex((n) => n + 1); }}
          />
        )}
      </div>
    </main>
  );
}
