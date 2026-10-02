/**
 * A canvas plan made after its reply (Sanya, 2 Oct 2026): polled until READY,
 * drawn against the reply it belongs to, and dropped silently whenever the
 * turn it was for is over.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const speech = vi.hoisted(() => ({
  progress: null as number | null,
  stopListeners: new Set<() => void>(),
}));
const backend = vi.hoisted(() => ({
  responses: [] as unknown[],
  calls: 0,
  sentListeners: new Set<() => void>(),
}));

vi.mock('@/lib/tts', () => ({
  tutorSpeechProgress: () => speech.progress,
  onTutorSpeechStop: (listener: () => void) => {
    speech.stopListeners.add(listener);
    return () => speech.stopListeners.delete(listener);
  },
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  fetchDeferredCanvasTeachingPlan: async () => {
    backend.calls += 1;
    const next = backend.responses.length > 1 ? backend.responses.shift() : backend.responses[0];
    if (next instanceof Error) throw next;
    return next;
  },
  onInteractionSent: (listener: () => void) => {
    backend.sentListeners.add(listener);
    return () => backend.sentListeners.delete(listener);
  },
}));

import { awaitDeferredTeachingPlan, cancelDeferredTeachingPlan } from '@/lib/deferredCanvasPlan';
import { cancelTeachingPlan } from '@/lib/canvasTeachingScheduler';
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
  beats: [beat('b1', 0, 'T1'), beat('b2', 36, 'T2')],
};

const REPLY = {
  interaction_state_version: 3,
  accepted_turn_id: 'TURN-1',
  canvas_teaching_plan_pending: true,
  message_voice: NARRATION,
};

const status = (s: 'PENDING' | 'READY' | 'UNAVAILABLE', plan: CanvasTeachingPlan | null = null) => ({
  status: s, accepted_turn_id: 'TURN-1', interaction_state_version: 3, question_id: 'Q1',
  canvas_teaching_plan: plan,
});

const marked = () => useNumeraStore.getState().teachingMarks.map((m) => m.tokenId);
const speaking = (on: boolean) => useMicLevel.getState().setAiSpeaking(on);
/** Let the in-flight poll resolve, then move the clock. */
const tick = async (ms: number) => { await vi.advanceTimersByTimeAsync(ms); };

beforeEach(() => {
  vi.useFakeTimers();
  speech.progress = null;
  speech.stopListeners.clear();
  backend.responses = [];
  backend.calls = 0;
  backend.sentListeners.clear();
  useMicLevel.getState().setAiSpeaking(false);
  useNumeraStore.getState().reset();
  useNumeraStore.getState().applyBackendPhase({
    phase: 'GUIDED_PRACTICE', questionId: 'Q1', questionText: 'n + 5', questionType: null,
  });
  useNumeraStore.setState({
    sessionId: 'SESSION-1',
    questionAnchors: [
      { token_id: 'T1', text: 'n', char_start: 0, char_end: 1 },
      { token_id: 'T2', text: '5', char_start: 4, char_end: 5 },
    ],
    appliedResponse: { version: 3, appliedTurnIds: new Set(['TURN-1']) },
  });
});

afterEach(() => {
  cancelDeferredTeachingPlan();
  cancelTeachingPlan();
  vi.useRealTimers();
});

describe('collecting a deferred canvas plan', () => {
  it('does nothing for a reply that is not pending', async () => {
    awaitDeferredTeachingPlan({ ...REPLY, canvas_teaching_plan_pending: false });
    await tick(1000);
    expect(backend.calls).toBe(0);
  });

  it('polls through PENDING and draws the READY plan with the speech', async () => {
    backend.responses = [status('PENDING'), status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    await tick(700);
    expect(backend.calls).toBe(3);
    expect(marked()).toEqual([]); // waiting for the tutor to speak
    speech.progress = 0;
    speaking(true);
    expect(marked()).toEqual(['T1']);
    speaking(false);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('joins a line already being spoken at its current position', async () => {
    backend.responses = [status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    speech.progress = 0;
    speaking(true);
    speech.progress = 0.3;
    await tick(400);
    expect(marked()).toEqual(['T1']);
    speech.progress = 0.7;
    await tick(200);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('draws the whole plan at once when the line had already finished', async () => {
    backend.responses = [status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    speech.progress = 0;
    speaking(true);
    speaking(false);
    await tick(400);
    expect(marked()).toEqual(['T1', 'T2']);
  });

  it('drops the plan when the tutor was cut off before it arrived', async () => {
    backend.responses = [status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    speaking(true);
    speech.stopListeners.forEach((l) => l());
    speaking(false);
    await tick(1000);
    expect(marked()).toEqual([]);
  });

  it('stops on UNAVAILABLE', async () => {
    backend.responses = [status('UNAVAILABLE')];
    awaitDeferredTeachingPlan(REPLY);
    await tick(2000);
    expect(backend.calls).toBe(1);
  });

  it('keeps asking through a failed read, and gives up after 20 seconds', async () => {
    backend.responses = [new Error('network')];
    awaitDeferredTeachingPlan(REPLY);
    await tick(25_000);
    const calls = backend.calls;
    expect(calls).toBeGreaterThan(10);
    await tick(5_000);
    expect(backend.calls).toBe(calls);
  });

  it('stops when the student starts a new turn', async () => {
    backend.responses = [status('PENDING'), status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    await tick(0);
    backend.sentListeners.forEach((l) => l());
    await tick(2000);
    expect(backend.calls).toBe(1);
    expect(marked()).toEqual([]);
  });

  it('stops when a newer reply arrives', async () => {
    backend.responses = [status('PENDING')];
    awaitDeferredTeachingPlan(REPLY);
    await tick(0);
    awaitDeferredTeachingPlan({ ...REPLY, accepted_turn_id: 'TURN-2', canvas_teaching_plan_pending: false });
    await tick(2000);
    expect(backend.calls).toBe(1);
  });

  it('does not draw a plan for a question the student has left', async () => {
    backend.responses = [status('PENDING'), status('READY', PLAN)];
    awaitDeferredTeachingPlan(REPLY);
    await tick(0);
    useNumeraStore.getState().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q2', questionText: 'm + 7', questionType: null,
    });
    await tick(20_000);
    expect(marked()).toEqual([]);
    expect(backend.calls).toBe(2);
  });

  it('does not draw a plan whose revision is no longer on screen', async () => {
    backend.responses = [status('READY', PLAN)];
    useNumeraStore.setState({ appliedResponse: { version: 4, appliedTurnIds: new Set(['TURN-1']) } });
    awaitDeferredTeachingPlan(REPLY);
    await tick(16_000);
    expect(marked()).toEqual([]);
  });
});
