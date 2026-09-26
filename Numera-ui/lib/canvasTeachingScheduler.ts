/**
 * Firing canvas teaching beats in time with the tutor's voice (handoff:
 * "Schedule the beat against audio playback at that phrase").
 *
 * One plan is live at a time — the latest turn's. Its life:
 *
 *   waiting  — the reply has been applied but the tutor has not started
 *              speaking it yet (synthesis, streaming, fallback voice). The
 *              stopTutorSpeech() that every new line begins with lands here,
 *              and is NOT an interruption: nothing has been said.
 *   speaking — the first rising edge of `aiSpeaking` after scheduling. A beat
 *              fires once playback passes the start of its phrase.
 *   done     — the line finished: every phrase has been said, so any beat not
 *              yet drawn is drawn now. Or it was cut off (stopTutorSpeech while
 *              speaking): marks already drawn stay, unstarted beats are
 *              discarded, exactly as the handoff asks.
 *
 * A reply the student never hears — voice unavailable, nothing ever plays — is
 * drawn after NO_SPEECH_MS, so the board still shows what the words said.
 *
 * Before every beat the scene is re-checked (phase, question, response
 * version). The student can move on while the tutor is still talking, and a
 * beat for the question just left must never land on the next one.
 */

import {
  beatStart, planMatchesResponse, planStillVisible,
  type CanvasTeachingBeat, type CanvasTeachingPlan, type ResponseScene,
} from '@/lib/canvasTeachingPlan';
import { onTutorSpeechStop, tutorSpeechProgress } from '@/lib/tts';
import { useMicLevel } from '@/store/useMicLevel';
import { useNumeraStore } from '@/store/useNumeraStore';

/** How often playback is sampled. An interval, not rAF: rAF stops in a hidden tab. */
const TICK_MS = 100;
/** Past the tts arrival guard (12 s), so a slow first chunk is not mistaken for silence. */
const NO_SPEECH_MS = 15_000;

interface LivePlan {
  plan: CanvasTeachingPlan;
  narrationLength: number;
  pending: CanvasTeachingBeat[];
  speaking: boolean;
  teardown: () => void;
}

let live: LivePlan | null = null;

/** Stop tracking the live plan. Marks already drawn stay where they are. */
export function cancelTeachingPlan(): void {
  live?.teardown();
  live = null;
}

/**
 * Take a turn's plan and draw it along with the speech.
 *
 * `narration` is the response's `message_voice` — the string the anchors index.
 * Returns whether the plan was accepted.
 */
export function scheduleTeachingPlan(
  plan: CanvasTeachingPlan | null | undefined,
  response: ResponseScene,
  narration: string | null | undefined,
): boolean {
  // A new reply supersedes the previous plan whether or not it carries one:
  // its unstarted beats belonged to words that are no longer being said.
  cancelTeachingPlan();
  if (!plan || !planMatchesResponse(plan, response)) return false;
  const accepted = plan;

  if (accepted.mode === 'replace') useNumeraStore.getState().replaceTeachingLayer();

  const beats = [...accepted.beats].sort((a, b) => a.sequence - b.sequence);
  const narrationLength = narration?.length
    || Math.max(1, ...beats.map((b) => b.speech_anchor?.end_char ?? 0));

  let timer: ReturnType<typeof setInterval> | null = null;
  const unsubscribes: Array<() => void> = [];
  const noSpeech = setTimeout(() => finish(true), NO_SPEECH_MS);

  const entry: LivePlan = {
    plan: accepted,
    narrationLength,
    pending: beats,
    speaking: false,
    teardown: () => {
      clearTimeout(noSpeech);
      if (timer) clearInterval(timer);
      unsubscribes.forEach((off) => off());
    },
  };
  live = entry;

  function finish(drawRest: boolean): void {
    if (live !== entry) return;
    if (drawRest) fireUpTo(1);
    cancelTeachingPlan();
  }

  function fireUpTo(progress: number): void {
    while (entry.pending.length && beatStart(entry.pending[0], narrationLength) <= progress) {
      const beat = entry.pending.shift()!;
      const s = useNumeraStore.getState();
      const scene = { phase: s.currentPhase, questionId: s.activeQuestionId, version: s.appliedResponse.version };
      if (!planStillVisible(accepted, scene)) {
        entry.pending = [];
        return;
      }
      s.applyTeachingBeat(accepted, beat);
    }
  }

  unsubscribes.push(useMicLevel.subscribe((state, prev) => {
    if (live !== entry) return;
    if (state.aiSpeaking && !prev.aiSpeaking && !entry.speaking) {
      entry.speaking = true;
      clearTimeout(noSpeech);
      fireUpTo(tutorSpeechProgress() ?? 0);
      timer = setInterval(() => {
        const progress = tutorSpeechProgress();
        if (progress !== null) fireUpTo(progress);
      }, TICK_MS);
    } else if (!state.aiSpeaking && prev.aiSpeaking && entry.speaking) {
      // Finished on its own — every phrase has been said.
      finish(true);
    }
  }));

  unsubscribes.push(onTutorSpeechStop(() => {
    // Cut off mid-line: keep what is drawn, drop what was not yet said.
    if (live === entry && entry.speaking) finish(false);
  }));

  return true;
}
