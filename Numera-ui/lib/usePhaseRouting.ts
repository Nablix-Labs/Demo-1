'use client';

/**
 * usePhaseRouting — put the student on the page for the backend's current phase.
 *
 * The backend and the Student Model own the phase; the frontend follows. Mounted
 * once in AppFrame so it watches every flow screen.
 *
 * It used to skip the FIRST observed phase and only follow FORWARD moves, to
 * avoid yanking a student off the guided page when their session opened in
 * DIAGNOSTIC. That was backwards: a student whose session is in DIAGNOSTIC
 * belongs on the diagnostic. The skip is why Manjusha logged in and got the
 * diagnostic question rendered on the guided lesson canvas instead of the
 * diagnostic screen (2026-07-28), and why the phase never appeared to change.
 *
 * Now it follows every phase the backend reports, in both directions — the loop
 * genuinely goes backwards (Feedback & Review sends a weak result back to
 * CONCEPT_ORIENTATION), so forward-only could never express it.
 */

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { phasesToUnlock, type FlowStage } from '@/lib/flow';

// Backend current_phase -> the manual flow stage it corresponds to. Following
// the backend has to unlock the client-side phase gates too: those are driven by
// `phasesDone`, which only goStage() writes. Without this the backend routes a
// student to /orientation and PhaseGate immediately tells them "ORIENTATION
// LOCKED — finish diagnostic first", for a diagnostic the backend just accepted.
const PHASE_STAGE: Record<string, FlowStage> = {
  DIAGNOSTIC: 'topic-diagnostic',
  CONCEPT_ORIENTATION: 'orientation',
  TEACH_BACK: 'teach',
  GUIDED_PRACTICE: 'guided',
  INDEPENDENT_PRACTICE: 'practice',
  REVIEW: 'review',
};

// Backend current_phase -> the route where that phase's work happens.
const PHASE_ROUTE: Record<string, (topicId: string) => string> = {
  DIAGNOSTIC: (t) => `/diagnostic/${t}`,
  CONCEPT_ORIENTATION: (t) => `/orientation/${t}`,
  TEACH_BACK: (t) => `/teach/${t}`,
  GUIDED_PRACTICE: () => '/',
  INDEPENDENT_PRACTICE: () => '/practice',
  REVIEW: () => '/review',
};

// Student Model phase names (PHASE_0_DIAGNOSTIC, …) as they appear on the login
// response's `last_journey_state`, mapped to the tutoring backend's own names.
const JOURNEY_PHASE: Record<string, string> = {
  PHASE_0_DIAGNOSTIC: 'DIAGNOSTIC',
  PHASE_1_ORIENTATION: 'CONCEPT_ORIENTATION',
  PHASE_2_GUIDED_LEARNING: 'GUIDED_PRACTICE',
  PHASE_3_INDEPENDENT_PRACTICE: 'INDEPENDENT_PRACTICE',
  REVIEW: 'REVIEW',
};

/**
 * Where a student belongs right now, and the client phase gates to open so they
 * aren't bounced straight back out (PhaseGate reads `phasesDone`, which only the
 * manual flow writes).
 *
 * `journeyPhase` is the Student Model's own name from `last_journey_state`.
 * A student with no journey has never started the topic, so they land on the
 * diagnostic — that is the first screen of the loop, and sending them to the
 * guided lesson instead is what showed Manjusha a stale practice question and no
 * diagnostic at all (2026-07-28).
 */
export function landingRoute(
  journeyPhase: string | null | undefined,
  topicId: string,
): { href: string; unlock: FlowStage } {
  const phase = journeyPhase ? JOURNEY_PHASE[journeyPhase] : undefined;
  const resolved = phase ?? 'DIAGNOSTIC';
  return {
    href: PHASE_ROUTE[resolved]?.(topicId) ?? `/diagnostic/${topicId}`,
    unlock: PHASE_STAGE[resolved] ?? 'topic-diagnostic',
  };
}

/**
 * Where a `next_topic_handoff` sends the student.
 *
 * Deliberately `landingRoute`, not a new mapping. The Student Model phase names
 * on the handoff are the same ones `last_journey_state` carries, and there are
 * already two maps between those and this app's routes; a third would be a
 * third thing to keep in step, and the one most likely to be missed when a
 * phase is added.
 *
 * Null when there is nothing to route to, so the caller keeps whatever it would
 * have done — which for a finished curriculum is the completion screen.
 */
export function handoffDestination(
  handoff: { topic_id?: string; entry_phase?: string } | null | undefined,
): { topicId: string; href: string; unlock: FlowStage } | null {
  const topicId = handoff?.topic_id?.trim();
  if (!topicId) return null;
  return { topicId, ...landingRoute(handoff?.entry_phase, topicId) };
}

const apiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

export function usePhaseRouting(): void {
  const router = useRouter();
  const pathname = usePathname();
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  useEffect(() => {
    if (!apiEnabled) return;
    const stage = PHASE_STAGE[currentPhase];
    if (stage) {
      const { completePhase } = useNumeraStore.getState();
      phasesToUnlock(stage).forEach(completePhase);
    }
    const target = PHASE_ROUTE[currentPhase]?.(currentTopicId);
    if (target && target !== pathname) router.push(target);
  }, [currentPhase, currentTopicId, pathname, router]);
}
