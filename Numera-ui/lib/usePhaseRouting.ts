'use client';

/**
 * usePhaseRouting — route the student to the page for the backend's current
 * phase, so navigation follows the backend rather than only in-screen buttons.
 *
 * The backend owns the phase (session_service picks the question by phase); this
 * keeps the frontend on the matching page as that phase advances. Mounted once
 * in AppFrame so it watches every flow screen.
 *
 * Forward-only, and skips the first observed value. The backend starts every
 * session in DIAGNOSTIC, so navigating on any change would yank a student who
 * loaded the guided page straight to /diagnostic the moment their session
 * starts. We only follow forward moves through PHASE_ORDER (e.g. DIAGNOSTIC ->
 * INDEPENDENT_PRACTICE), which is what the loop actually does.
 */

import { useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';

// Canonical order of the backend's phases; used to allow only forward moves.
const PHASE_ORDER = [
  'DIAGNOSTIC',
  'CONCEPT_ORIENTATION',
  'TEACH_BACK',
  'GUIDED_PRACTICE',
  'INDEPENDENT_PRACTICE',
  'REVIEW',
] as const;

// Backend current_phase -> the route where that phase's work happens.
const PHASE_ROUTE: Record<string, (topicId: string) => string> = {
  DIAGNOSTIC: (t) => `/diagnostic/${t}`,
  CONCEPT_ORIENTATION: (t) => `/orientation/${t}`,
  TEACH_BACK: (t) => `/teach/${t}`,
  GUIDED_PRACTICE: () => '/',
  INDEPENDENT_PRACTICE: () => '/practice',
  REVIEW: () => '/review',
};

const apiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

export function usePhaseRouting(): void {
  const router = useRouter();
  const pathname = usePathname();
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const prevPhase = useRef<string | null>(null);

  useEffect(() => {
    if (!apiEnabled) return;
    const prev = prevPhase.current;
    prevPhase.current = currentPhase;
    // Skip the session-start seed and no-op re-renders.
    if (prev === null || prev === currentPhase) return;
    // Forward moves only (see file header).
    if (PHASE_ORDER.indexOf(currentPhase as never) <= PHASE_ORDER.indexOf(prev as never)) return;
    const target = PHASE_ROUTE[currentPhase]?.(currentTopicId);
    if (target && target !== pathname) router.push(target);
  }, [currentPhase, currentTopicId, pathname, router]);
}
