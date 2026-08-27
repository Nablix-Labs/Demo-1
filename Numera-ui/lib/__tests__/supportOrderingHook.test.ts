/**
 * The ORDER the reply paths actually use — not the order a test chooses.
 *
 * A previous version of this check called applyInteractionSupport and
 * addTranscriptMessage itself and asserted they happened in that order, which
 * proves nothing about the code under test. This drives the real hook and
 * watches the store, so it fails if any path goes back to appending the tutor's
 * line before the support that line refers to.
 */

import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const sendInteraction = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  sendInteraction: (...args: unknown[]) => sendInteraction(...args),
}));
// Real module except the two that reach a speech engine — see canvasPhaseSync.
vi.mock('@/lib/tutorSpeech', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/tutorSpeech')>()),
  setStudentWriting: vi.fn(),
  tutorSay: vi.fn(),
}));

import { useDemoTutor } from '@/hooks/useDemoTutor';
import type { InteractionResponse } from '@/lib/api';
import { useNumeraStore } from '@/store/useNumeraStore';

/** A turn that serves a cue and then talks about it. */
const CTX = { concept_id: 'ALG_LINEAR_ONE_STEP', current_phase: 'GUIDED_PRACTICE', hint_count: 0 };

const replyWithCue = (overrides: Record<string, unknown> = {}) => ({
  session_id: 'SESSION001',
  student_id: 'ST001',
  status: 'processed',
  message: 'Look at the visual cue on your screen.',
  message_voice: 'Look at the visual cue on your screen.',
  conversation_action: 'GIVE_HINT',
  current_phase: 'GUIDED_PRACTICE',
  current_question: 'Write the general rule.',
  question_id: 'Q-T01-004',
  interaction_state_version: 1,
  visual_cue: { show: true, cue_type: 'DIAGRAM', description: 'A number line from 0 to 10.' },
  ...overrides,
});

describe('every reply path shows support before the message', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  beforeEach(async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    sendInteraction.mockReset();
    tutor = null;
    useNumeraStore.setState({
      sessionId: 'SESSION001',
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-T01-004',
      questionText: 'Write the general rule.',
      transcript: [],
      visualCueVisible: false,
      visualCueDescription: null,
      appliedResponse: { version: null, appliedTurnIds: new Set<string>() },
    });
    const container = document.createElement('div');
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(() => { tutor = useDemoTutor(); return null; }));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  /** Records which of the two landed in the store first. */
  function watchOrder() {
    const order: string[] = [];
    const unsubscribe = useNumeraStore.subscribe((state, prev) => {
      if (state.visualCueVisible && !prev.visualCueVisible) order.push('cue');
      if (state.transcript.some((m) => m.role === 'ai')
          && !prev.transcript.some((m) => m.role === 'ai')) order.push('message');
    });
    return { order, unsubscribe };
  }

  it('answer(): cue before the tutor line', async () => {
    sendInteraction.mockResolvedValue(replyWithCue());
    const { order, unsubscribe } = watchOrder();
    await act(async () => { await tutor?.answer('n plus four', CTX); });
    unsubscribe();
    expect(order[0]).toBe('cue');
    expect(order).toContain('message');
  });

  it('selectOption(): cue before the tutor line — this path applied no support at all', async () => {
    sendInteraction.mockResolvedValue(replyWithCue({ interaction_state_version: 2 }));
    const { order, unsubscribe } = watchOrder();
    await act(async () => { await tutor?.selectOption('B', 'n + 4'); });
    unsubscribe();
    expect(order[0]).toBe('cue');
  });

  it('submits a Phase 3 choice without tutor feedback and applies REVIEW', async () => {
    useNumeraStore.setState({
      currentPhase: 'INDEPENDENT_PRACTICE',
      activeQuestionId: 'Q-T01-008',
      transcript: [],
    });
    sendInteraction.mockResolvedValue(replyWithCue({
      current_phase: 'REVIEW',
      current_question: null,
      question_id: null,
      phase3_submission_confirmed: true,
      phase3_submission_kind: 'CHOICE',
      independent_outcome: 'INDEPENDENTLY_VERIFIED',
      interaction_state_version: 2,
    }));

    let response: InteractionResponse | null | undefined;
    await act(async () => { response = await tutor?.selectOption('B', 'p decreases by 2'); });

    expect(sendInteraction).toHaveBeenCalledWith(expect.objectContaining({
      interaction_type: 'OPTION_SELECTED',
      input_source: 'CHOICE',
      selected_option_id: 'B',
      selected_option_text: 'p decreases by 2',
      current_phase: 'INDEPENDENT_PRACTICE',
      question_id: 'Q-T01-008',
    }));
    expect(response).toMatchObject({ current_phase: 'REVIEW' });
    expect(useNumeraStore.getState().currentPhase).toBe('REVIEW');
    expect(useNumeraStore.getState().transcript).toEqual([]);
  });

  it('hint(): cue before the tutor line', async () => {
    sendInteraction.mockResolvedValue(replyWithCue({ interaction_state_version: 3 }));
    const { order, unsubscribe } = watchOrder();
    await act(async () => { await tutor?.hint(); });
    unsubscribe();
    expect(order[0]).toBe('cue');
  });

  it('submitTeachBack(): cue before the tutor line', async () => {
    sendInteraction.mockResolvedValue(replyWithCue({ interaction_state_version: 4 }));
    const { order, unsubscribe } = watchOrder();
    await act(async () => { await tutor?.submitTeachBack('because it grows by four'); });
    unsubscribe();
    expect(order[0]).toBe('cue');
  });

  it('shows no cue when the turn served none', async () => {
    sendInteraction.mockResolvedValue(replyWithCue({ visual_cue: undefined, interaction_state_version: 5 }));
    await act(async () => { await tutor?.answer('n plus four', CTX); });
    expect(useNumeraStore.getState().visualCueVisible).toBe(false);
  });

  it('shows an authorised hint without the student pressing Need help?', async () => {
    // WRONG_1: the backend serves a real hint alongside its own correction.
    sendInteraction.mockResolvedValue(replyWithCue({
      interaction_state_version: 6,
      visual_cue: undefined,
      message: 'Not quite — think about what changes each time.',
      support_message: 'Look at the operation in every example. Is it addition or multiplication?',
      conversation_action: 'GIVE_HINT',
    }));
    await act(async () => { await tutor?.answer('12 + 5', CTX); });

    const said = useNumeraStore.getState().transcript.filter((m) => m.role === 'ai').map((m) => m.text);
    expect(said[0]).toContain('Is it addition or multiplication?');
    expect(said[1]).toBe('Not quite — think about what changes each time.');
    // Still available for the Need help? replay.
    expect(useNumeraStore.getState().lastHintText).toContain('addition or multiplication');
  });

  it('does not invent a hint when the backend served none', async () => {
    sendInteraction.mockResolvedValue(replyWithCue({
      interaction_state_version: 7,
      visual_cue: undefined,
      message: 'Keep going.',
      conversation_action: 'ASK_QUESTION',
    }));
    await act(async () => { await tutor?.answer('12 + 5', CTX); });
    const said = useNumeraStore.getState().transcript.filter((m) => m.role === 'ai').map((m) => m.text);
    expect(said).toEqual(['Keep going.']);
  });
});
