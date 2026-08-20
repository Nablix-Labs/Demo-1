/**
 * Coverage for the voice transport's session sync.
 *
 * This file exists because `useWebSocket` had none. Seven pieces of the REST
 * sync were lost on the voice path over three weeks, and every one could have
 * been deleted without a single test failing. Run against the real store, so a
 * regression in the WIRING fails here — not just in the helpers it calls.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { applyVoiceSessionFrame } from '@/lib/voiceSessionSync';
import { useNumeraStore } from '@/store/useNumeraStore';
import { REVEAL_MS } from '@/lib/revealBeforeClear';

const OPTIONS = [
  { option_id: 'A', text: 'n + 4' },
  { option_id: 'B', text: '4n' },
];

/** A frame carrying a new question set, as the streaming server spreads it. */
const frameWithNewSet = (over: Record<string, unknown> = {}) => ({
  current_phase: 'GUIDED_PRACTICE',
  question_id: 'Q2',
  current_question: 'Which is the general rule?',
  question_type: 'SINGLE_CHOICE',
  student_model_event: {
    phase_payload: {
      question_set: {
        questions: [{
          question_id: 'Q2',
          student_view: { question_type: 'SINGLE_CHOICE', options: OPTIONS },
        }],
      },
    },
  },
  ...over,
});

beforeEach(() => {
  useNumeraStore.getState().reset();
  useNumeraStore.setState({
    currentPhase: 'GUIDED_PRACTICE',
    activeQuestionId: 'Q1',
    backendSession: { session_id: 'S1', student_id: 'ST001' } as never,
  });
});

describe('a phase change that issues a new question set', () => {
  it('refreshes the cached record so the new question finds its options', () => {
    // The regression this file was written for. Options do not travel on a
    // reply; they are looked up out of the cached record by question id. Left
    // stale, the lookup searched the PREVIOUS phase's questions and the student
    // got a choice question with no choices under it — on the transport Guided
    // Practice mostly runs on.
    applyVoiceSessionFrame(frameWithNewSet(), (fn) => fn());
    expect(useNumeraStore.getState().questionOptions).toEqual(OPTIONS);
  });

  it('leaves the cached record alone when the frame carries no set', () => {
    // Overwriting on an event with no set would drop the options already held.
    useNumeraStore.setState({ questionOptions: OPTIONS as never });
    applyVoiceSessionFrame(
      { current_phase: 'GUIDED_PRACTICE', question_id: 'Q1' }, (fn) => fn(),
    );
    expect(useNumeraStore.getState().backendSession).toEqual({
      session_id: 'S1', student_id: 'ST001',
    });
  });
});

describe('the question counter', () => {
  it('follows the frame', () => {
    applyVoiceSessionFrame(frameWithNewSet({ question_number: 3 }), (fn) => fn());
    expect(useNumeraStore.getState().questionNumber).toBe(3);
  });

  it('is left alone when the frame omits it, rather than reset to zero', () => {
    useNumeraStore.setState({ questionNumber: 2 });
    applyVoiceSessionFrame(frameWithNewSet(), (fn) => fn());
    expect(useNumeraStore.getState().questionNumber).toBe(2);
  });
});

describe('the phase change', () => {
  it('applies immediately on an ordinary turn', () => {
    const held = applyVoiceSessionFrame(frameWithNewSet(), (fn) => fn());
    expect(held).toBe(0);
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q2');
  });

  it('is held when the turn also annotated the work it is leaving', () => {
    // Without the hold the marks are added and cleared in the same tick, and
    // the student sees a blank board instead of the point being made.
    let deferred: (() => void) | null = null;
    const held = applyVoiceSessionFrame(
      frameWithNewSet({ tutor_canvas_actions: [{ action_id: 'A1' }] }),
      (fn) => { deferred = fn; },
    );
    expect(held).toBe(REVEAL_MS);
    // The board has NOT moved on yet — that is the whole point.
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q1');
    deferred!();
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q2');
  });

  it('does not hold when the question is not changing', () => {
    const held = applyVoiceSessionFrame(
      frameWithNewSet({ question_id: 'Q1', tutor_canvas_actions: [{ action_id: 'A1' }] }),
      (fn) => fn(),
    );
    expect(held).toBe(0);
  });

  it('does nothing at all when the frame carries no phase', () => {
    // A frame without current_phase is not a phase update; applying one would
    // blank the question the student is working on.
    applyVoiceSessionFrame({ question_id: 'Q9' }, (fn) => fn());
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q1');
  });
});
