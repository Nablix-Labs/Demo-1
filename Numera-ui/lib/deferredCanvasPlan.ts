/**
 * Collecting a canvas teaching plan that was made AFTER its reply (Sanya,
 * 2 Oct 2026).
 *
 * Every /interaction request asks the backend to defer the plan, so the tutor's
 * words arrive without waiting for the planner. The reply then says
 * `canvas_teaching_plan_pending: true`, and the plan is fetched from
 * GET /interaction/{session}/canvas-teaching-plan/{turn} until it is READY.
 *
 * Only the plan is late. The reply — its words, its voice, its support — has
 * already been applied and is NOT applied again: a READY plan goes straight to
 * `scheduleTeachingPlan` with the reply it belongs to, exactly as an inline
 * plan would have.
 *
 * Polling stops, silently, on any of:
 *   - UNAVAILABLE or 404 (the planner made nothing, or the turn is unknown);
 *   - POLL_LIMIT_MS without a plan;
 *   - the student starting a new turn, or another reply arriving;
 *   - the question, phase or session changing;
 *   - the lesson screen unmounting (`cancelDeferredTeachingPlan`).
 * None of these is a tutor error. The student has the tutor's reply; what they
 * are missing is the drawing that goes with it, and a message about that would
 * be noise.
 *
 * One poll is live at a time, for the latest reply only.
 */

import { fetchDeferredCanvasTeachingPlan, onInteractionSent } from '@/lib/api';
import { planStillVisible, type ResponseScene } from '@/lib/canvasTeachingPlan';
import { scheduleTeachingPlan, type SpeechSoFar } from '@/lib/canvasTeachingScheduler';
import { onTutorSpeechStop } from '@/lib/tts';
import { useMicLevel } from '@/store/useMicLevel';
import { useNumeraStore } from '@/store/useNumeraStore';

/** Handoff: "Poll about every 300 ms, stopping after 20 seconds". */
export const POLL_INTERVAL_MS = 300;
export const POLL_LIMIT_MS = 20_000;

export interface DeferredPlanReply extends ResponseScene {
  canvas_teaching_plan_pending?: boolean | null;
  message_voice?: string | null;
}

interface LivePoll {
  stop: () => void;
}

let live: LivePoll | null = null;

/** Stop waiting for a deferred plan. Safe to call when none is pending. */
export function cancelDeferredTeachingPlan(): void {
  live?.stop();
  live = null;
}

/**
 * Start collecting the plan for `reply` if the backend deferred it.
 *
 * Called for every applied reply: a reply that is not pending still cancels
 * the previous poll, since its plan belonged to a turn that is now over.
 */
export function awaitDeferredTeachingPlan(reply: DeferredPlanReply): void {
  cancelDeferredTeachingPlan();
  if (reply.canvas_teaching_plan_pending !== true) return;

  const start = useNumeraStore.getState();
  const sessionId = start.sessionId;
  const turnId = reply.accepted_turn_id ?? null;
  if (!sessionId || !turnId) {
    console.info('[canvas-plan] deferred plan not collected: reply has no session or turn id', {
      session_id: sessionId, accepted_turn_id: turnId,
    });
    return;
  }

  const startedAt = Date.now();
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  // Follow the tutor's line from the moment the reply lands, so a plan that
  // arrives mid-line or after it can be joined at the right place.
  let speech: SpeechSoFar['speech'] = 'waiting';
  const offSpeaking = useMicLevel.subscribe((state, prev) => {
    if (state.aiSpeaking && !prev.aiSpeaking && speech === 'waiting') speech = 'speaking';
    else if (!state.aiSpeaking && prev.aiSpeaking && speech === 'speaking') speech = 'done';
  });
  // Cut off mid-line: the scheduler would discard every beat not yet said, and
  // for a plan that has not arrived that is all of them.
  const offStop = onTutorSpeechStop(() => {
    if (speech === 'speaking') finish('the tutor was cut off');
  });

  const offSent = onInteractionSent(() => finish('a new turn started'));

  const entry: LivePoll = {
    stop: () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      offSpeaking();
      offStop();
      offSent();
    },
  };
  live = entry;

  function finish(reason: string | null): void {
    if (live !== entry) return;
    if (reason) console.info('[canvas-plan] deferred plan dropped:', reason, { turn_id: turnId });
    cancelDeferredTeachingPlan();
  }

  /**
   * Why this turn's plan can no longer be drawn, or null if it still can.
   * `questionId` is the backend's, from the poll — the reply's own question
   * may not be on screen yet when the first poll goes out.
   */
  function movedOn(questionId?: string | null): string | null {
    const s = useNumeraStore.getState();
    if (s.sessionId !== sessionId) return 'the session changed';
    if (s.currentPhase !== 'GUIDED_PRACTICE') return 'the phase changed';
    if (questionId && s.activeQuestionId && s.activeQuestionId !== questionId) return 'the question changed';
    return null;
  }

  async function poll(): Promise<void> {
    if (stopped) return;
    const moved = movedOn();
    if (moved) return finish(moved);
    if (Date.now() - startedAt > POLL_LIMIT_MS) return finish(`no plan after ${POLL_LIMIT_MS / 1000}s`);

    let status;
    try {
      status = await fetchDeferredCanvasTeachingPlan(sessionId!, turnId!);
    } catch {
      // A failed read is not an answer. Keep asking until the time limit.
      status = null;
    }
    if (stopped) return;

    if (status?.status === 'UNAVAILABLE') return finish(null);
    const movedSince = movedOn(status?.question_id);
    if (movedSince) return finish(movedSince);
    if (status?.status === 'READY' && status.canvas_teaching_plan) {
      const plan = status.canvas_teaching_plan;
      const s = useNumeraStore.getState();
      const scene = {
        phase: s.currentPhase, questionId: s.activeQuestionId, version: s.appliedResponse.version,
      };
      if (plan.source_turn_id !== turnId || !planStillVisible(plan, scene)) {
        return finish('it no longer matches the screen');
      }
      const soFar: SpeechSoFar = { speech, since: startedAt };
      cancelDeferredTeachingPlan();
      scheduleTeachingPlan(plan, reply, reply.message_voice, soFar);
      return;
    }
    timer = setTimeout(() => { void poll(); }, POLL_INTERVAL_MS);
  }

  void poll();
}
