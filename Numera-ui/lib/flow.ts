/**
 * Flow — the per-topic loop state machine (see docs/LEARNING-FLOW.md).
 *
 * Pure logic only: given the current stage / topic / a decision, it returns the
 * next stage. The component layer (FlowControls) holds no rules — it just calls
 * these functions, writes the result to the store, and navigates.
 *
 * Per-topic loop:
 *   topic-diagnostic → orientation → guided → practice → review → (branch)
 * Entry topic (N) skips the topic-diagnostic; every later topic runs it.
 * Review branches: can't-solve → guided, foundation-weak → orientation,
 * pass → mastery → next topic.
 */

import { PHASE_ORDER, type LearningPhase } from './phases';

export type FlowStage =
  | 'topic-diagnostic'
  | 'orientation'
  | 'teach'
  | 'guided'
  | 'practice'
  | 'review';

export type ReviewOutcome = 'cant_solve' | 'foundation_weak' | 'pass';

/** Linear forward order used by the generic "skip stage" control. */
export const FORWARD: FlowStage[] = [
  'topic-diagnostic',
  'orientation',
  'teach',
  'guided',
  'practice',
  'review',
];

/**
 * Where a stage lives in the app.
 *
 * The three topic-scoped screens carry the topic as `?topic=`, not as a path
 * segment. This is a static export and topic ids are backend curriculum codes
 * from an open-ended set, so a dynamic segment has no HTML and no RSC payload
 * on disk for any real topic — and the App Router fetches that payload on a
 * client-side push, not just on a refresh. See components/TopicParamRoute for
 * what that produced on the deployed build.
 *
 * `topicId` is encoded: it comes from the Student Model and nothing guarantees
 * it is URL-safe.
 */
export function routeFor(stage: FlowStage, topicId: string): string {
  const topic = encodeURIComponent(topicId);
  switch (stage) {
    case 'topic-diagnostic':
      return `/topic-diagnostic/?topic=${topic}`;
    case 'orientation':
      return `/orientation/?topic=${topic}`;
    case 'teach':
      return `/teach/?topic=${topic}`;
    case 'guided':
      return '/';
    case 'practice':
      return '/practice';
    case 'review':
      return '/review';
  }
}

/** Entry stage when a topic begins: N skips straight to orientation. */
export function entryStage(topicId: string, entryTopicId: string | null): FlowStage {
  return topicId === entryTopicId ? 'orientation' : 'topic-diagnostic';
}

/** The next stage in the linear chain, or null at the end (review). */
export function nextStage(stage: FlowStage): FlowStage | null {
  const i = FORWARD.indexOf(stage);
  return i >= 0 && i + 1 < FORWARD.length ? FORWARD[i + 1] : null;
}

/** Topic-diagnostic result: knowing the concept skips orientation. */
export function afterDiagnostic(knowsConcept: boolean): FlowStage {
  return knowsConcept ? 'guided' : 'orientation';
}

/** Feedback & Review decision point — the three-way branch. */
export function afterReview(
  outcome: ReviewOutcome,
): { stage: FlowStage; advanceTopic: boolean } {
  switch (outcome) {
    case 'cant_solve':
      return { stage: 'guided', advanceTopic: false };
    case 'foundation_weak':
      return { stage: 'orientation', advanceTopic: false };
    case 'pass':
      return { stage: 'guided', advanceTopic: true }; // entry stage of next topic resolved by caller
  }
}

/**
 * The old linear-funnel phases (lib/phases.ts) still gate screens via PhaseGate.
 * To let the loop navigate freely during the demo, mark every phase up to and
 * including the target stage's anchor as done. Bridge only — drops out once the
 * gates become loop-aware.
 */
const STAGE_ANCHOR: Record<FlowStage, LearningPhase> = {
  'topic-diagnostic': 'diagnostic',
  orientation: 'orientation',
  teach: 'teach',
  guided: 'workbook',
  practice: 'practice',
  review: 'review',
};

export function phasesToUnlock(stage: FlowStage): LearningPhase[] {
  const idx = PHASE_ORDER.indexOf(STAGE_ANCHOR[stage]);
  return PHASE_ORDER.slice(0, idx + 1);
}
