/**
 * Beats fire when the voice reaches their phrase; an interruption keeps what
 * was drawn and drops the rest (handoff: "retain already-completed persistent
 * marks if the student interrupts the tutor and discard unstarted beats").
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const speech = vi.hoisted(() => ({
  progress: null as number | null,
  stopListeners: new Set<() => void>(),
}));

vi.mock('@/lib/tts', () => ({
  tutorSpeechProgress: () => speech.progress,
  onTutorSpeechStop: (listener: () => void) => {
    speech.stopListeners.add(listener);
    return () => speech.stopListeners.delete(listener);
  },
}));

import { cancelTeachingPlan, scheduleTeachingPlan } from '@/lib/canvasTeachingScheduler';
import type { CanvasTeachingPlan } from '@/lib/canvasTeachingPlan';
import { useMicLevel } from '@/store/useMicLevel';
import { useNumeraStore } from '@/store/useNumeraStore';

const NARRATION = 'Those first numbers change, but the plus five stays the same.';

const beat = (id: string, start: number, token: string) => ({
  beat_id: id,
  sequence: Number(id.slice(1)),
  speech_anchor: { start_char: start, end_char: start + 5, text: NARRATION.slice(start, start + 5) },
  operations: [{
    operation_id: `op-${id}`,
    kind: 'CIRCLE' as const,
    target_kind: 'QUESTION_ANCHOR' as const,
    target_ids: [token],
    zone: 'QUESTION' as const,
    persistence: 'PERSIST' as const,
    color_role: 'AMBER' as const,
  }],
});

const PLAN: CanvasTeachingPlan = {
  plan_id: 'Q1:TURN-1:canvas-teaching',
  question_id: 'Q1',
  source_turn_id: 'TURN-1',
  scene_revision: 3,
  mode: 'append',
  teaching_mode: 'GUIDED',
  // 0/62 ≈ 0, 36/62 ≈ 0.58
  beats: [beat('b1', 0, 'T1'), beat('b2', 36, 'T2')],
};

const RESPONSE = { interaction_state_version: 3, accepted_turn_id: 'TURN-1' };

const marked = () => useNumeraStore.getState().teachingMarks.map((m) => m.tokenId);
const speaking = (on: boolean) => useMicLevel.getState().setAiSpeaking(on);

beforeEach(() => {
  vi.useFakeTimers();
  speech.progress = null;
  speech.stopListeners.clear();
  useMicLevel.getState().setAiSpeaking(false);
  useNumeraStore.getState().reset();
  useNumeraStore.getState().applyBackendPhase({
    phase: 'GUIDED_PRACTICE', questionId: 'Q1', questionText: 'n + 5', questionType: null,
  });
  useNumeraStore.setState({
    questionAnchors: [
      { token_id: 'T1', text: 'n', char_start: 0, char_end: 1 },
      { token_id: 'T2', text: '5', char_start: 4, char_end: 5 },
    ],
    appliedResponse: { version: 3, appliedTurnIds: new Set(['TURN-1']) },
  });
});

afterEach(() => {
  cancelTeachingPlan();
  vi.useRealTimers();
});

describe('scheduling against the voice', () => {
  it('draws nothing before the tutor starts speaking', () => {
    expect(scheduleTeachingPlan(PLAN, RESPONSE, NARRATION)).toBe(true);
    vi.advanceTimersByTime(1000);
    expect(marked()).toEqual([]);
  });

  it('fires each beat as playback reaches its phrase', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    speech.progress = 0;
    speaking(true);
    expect(marked()).toEqual(['T1']);
    speech.progress = 0.4;
    vi.advanceTimersByTime(200);
    expect(marked()).toEqual(['T1']);
    speech.progress = 0.6;
    vi.advanceTimersByTime(200);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('keeps drawn marks and discards unstarted beats when interrupted', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    speech.progress = 0.1;
    speaking(true);
    speech.stopListeners.forEach((l) => l());
    speaking(false);
    speech.progress = 1;
    vi.advanceTimersByTime(20_000);
    expect(marked()).toEqual(['T1']);
  });

  it('does not count the stop that starts the line as an interruption', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    speech.stopListeners.forEach((l) => l()); // speakTutor stops before it plays
    speech.progress = 0;
    speaking(true);
    expect(marked()).toEqual(['T1']);
  });

  it('draws the rest when the line finishes on its own', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    speech.progress = 0;
    speaking(true);
    speaking(false);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('draws the plan anyway when no audio ever plays', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    vi.advanceTimersByTime(16_000);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('stops drawing once the question has moved on', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    speech.progress = 0;
    speaking(true);
    useNumeraStore.getState().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q2', questionText: 'm + 7', questionType: null,
    });
    speech.progress = 1;
    vi.advanceTimersByTime(200);
    expect(marked()).toEqual([]);
  });

  it('refuses a plan for a different revision', () => {
    expect(scheduleTeachingPlan(PLAN, { interaction_state_version: 4 }, NARRATION)).toBe(false);
  });

  it('draws a beat once even if the same plan is replayed', () => {
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    vi.advanceTimersByTime(16_000);
    scheduleTeachingPlan(PLAN, RESPONSE, NARRATION);
    vi.advanceTimersByTime(16_000);
    expect(marked()).toEqual(['T1', 'T2']);
  });
});
