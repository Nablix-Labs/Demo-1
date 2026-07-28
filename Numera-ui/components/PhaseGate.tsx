'use client';

/**
 * PhaseGate — guards a learning-flow screen until its prerequisite phase is
 * complete (see lib/phases.ts). While the persisted store rehydrates it shows a
 * neutral loading skeleton (no flash of the gate). If a prerequisite is missing
 * it renders a gate screen pointing the student at the next step, plus a
 * "Continue anyway" bypass that marks the outstanding phases done.
 */

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { Lock, ArrowRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { PHASE_META, missingPrereqs, type LearningPhase } from '@/lib/phases';
import { Skeleton } from '@/components/PageShell';

function GateSkeleton() {
  return (
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-busy="true" aria-label="Loading">
      <div className="w-[460px] max-w-full flex flex-col items-center gap-4">
        <Skeleton className="w-12 h-12 rounded-xl" />
        <Skeleton className="w-48 h-5" />
        <Skeleton className="w-72 h-3" />
        <Skeleton className="w-full h-12 rounded-md mt-2" />
      </div>
    </main>
  );
}

/**
 * With a backend, the phase is not ours to gate.
 *
 * `phasesDone` is written only by the manual mock flow (goStage), so a student
 * whose phase comes from the Student Model has it empty — and the gate then
 * blocks the very screen the backend just routed them to. Worse, it blocks the
 * children from mounting, so the screen never opens a session, the phase never
 * changes, and nothing can ever unlock it: a deadlock that showed a returning
 * student "ORIENTATION LOCKED — finish diagnostic first" for a diagnostic they
 * had already completed (2026-07-28).
 *
 * usePhaseRouting already keeps the student on the page matching the backend's
 * current_phase, which is the real gate. This one is mock-mode scaffolding.
 */
const apiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

export default function PhaseGate({
  phase,
  children,
}: {
  phase: LearningPhase;
  children: ReactNode;
}) {
  const phasesDone = useNumeraStore((s) => s.phasesDone);
  const completePhase = useNumeraStore((s) => s.completePhase);

  // Backend-driven builds never gate (see above). Declared after the hooks so
  // the hook order stays stable.
  // The store rehydrates on the client (skipHydration); wait for it so we don't
  // gate a student who has actually completed the prerequisite.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (useNumeraStore.persist.hasHydrated()) setHydrated(true);
    return useNumeraStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  if (apiEnabled) return <>{children}</>;
  if (!hydrated) return <GateSkeleton />;

  const missing = missingPrereqs(phase, phasesDone);
  if (missing.length === 0) return <>{children}</>;

  const next = PHASE_META[missing[0]];
  const here = PHASE_META[phase];

  return (
    <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label={`${here.label} locked`}>
      <div className="w-[460px] max-w-full text-center">
        <div className="w-12 h-12 mx-auto rounded-xl border border-muted-gray bg-reading-surface text-slate-blue flex items-center justify-center mb-4">
          <Lock size={20} strokeWidth={1.8} />
        </div>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">{here.label} locked</div>
        <h1 className="text-[22px] font-semibold text-ink">Finish {next.label.toLowerCase()} first</h1>
        <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">{next.blurb}</p>

        <Link
          href={next.href}
          className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-4 py-3 text-[13px] font-semibold hover:opacity-80 transition-opacity"
        >
          {next.cta} <ArrowRight size={16} strokeWidth={2} />
        </Link>

        {/* Bypass the funnel during development. */}
        <button
          onClick={() => missing.forEach(completePhase)}
          className="mt-3 w-full rounded-md border border-muted-gray bg-white px-4 py-2.5 text-[12px] font-semibold text-slate-blue hover:text-ink hover:border-slate-blue transition-colors"
        >
          Continue anyway
        </button>
      </div>
    </main>
  );
}
