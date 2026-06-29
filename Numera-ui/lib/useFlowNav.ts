'use client';

/**
 * useFlowNav — the single navigation brain for the adaptive loop.
 *
 * Both the in-screen "Continue" CTAs and the Demo Director (FlowControls) call
 * this, so the loop behaves identically however it's driven. All rules live in
 * lib/flow.ts; this binds them to the store + router.
 */

import { useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { nextTopicId } from '@/lib/topics';
import {
  routeFor,
  nextStage,
  entryStage,
  afterDiagnostic,
  afterReview,
  phasesToUnlock,
  type FlowStage,
  type ReviewOutcome,
} from '@/lib/flow';

export function useFlowNav() {
  const router = useRouter();
  const entryTopicId = useNumeraStore((s) => s.entryTopicId);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const flowStage = useNumeraStore((s) => s.flowStage);
  const masteryByTopic = useNumeraStore((s) => s.masteryByTopic);
  const setEntryTopic = useNumeraStore((s) => s.setEntryTopic);
  const setCurrentTopic = useNumeraStore((s) => s.setCurrentTopic);
  const setFlowStage = useNumeraStore((s) => s.setFlowStage);
  const setMastery = useNumeraStore((s) => s.setMastery);
  const completePhase = useNumeraStore((s) => s.completePhase);

  /** Unlock the legacy gates, record stage + topic, route there. */
  const goStage = (stage: FlowStage, topicId: string = currentTopicId) => {
    phasesToUnlock(stage).forEach(completePhase);
    setCurrentTopic(topicId);
    setFlowStage(stage);
    router.push(routeFor(stage, topicId));
  };

  /** Mock Main Diagnostic: place the student at topic N → its orientation. */
  const placeAtTopic = (id: string) => {
    setEntryTopic(id);
    phasesToUnlock('orientation').forEach(completePhase);
    router.push(routeFor('orientation', id));
  };

  /** Generic forward step (used by "Skip stage" / a screen's plain Continue). */
  const advance = () => {
    const n = nextStage(flowStage);
    if (n) goStage(n);
  };

  /** Topic-diagnostic outcome: knowing the concept skips orientation. */
  const decideDiagnostic = (knows: boolean, topicId: string = currentTopicId) =>
    goStage(afterDiagnostic(knows), topicId);

  /** Feedback & Review decision point — the three-way branch + mastery. */
  const decideReview = (outcome: ReviewOutcome) => {
    const { stage, advanceTopic } = afterReview(outcome);
    if (!advanceTopic) return goStage(stage);
    setMastery(currentTopicId, true);
    const next = nextTopicId(currentTopicId);
    if (!next) {
      router.push('/complete'); // every topic mastered — course complete
      return;
    }
    goStage(entryStage(next, entryTopicId), next);
  };

  return {
    entryTopicId,
    currentTopicId,
    flowStage,
    masteryByTopic,
    goStage,
    placeAtTopic,
    advance,
    decideDiagnostic,
    decideReview,
  };
}
