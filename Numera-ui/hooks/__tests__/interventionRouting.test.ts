/**
 * The pause, as it is set and cleared at the single reply choke point.
 *
 * The clearing rule is the delicate half. The request arrives on ONE reply and
 * then disappears (Chirudeva, 7 Sep), so anything that clears on a reply the
 * parser does not recognise takes the popup down on the student's very next
 * word — and every ordinary Phase 2 turn is unrecognised by design.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/lib/tts', () => ({ speakTutor: vi.fn(), stopTutorSpeech: vi.fn() }));

import { syncBackendSession } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

/** The parts of a reply this path reads. */
const reply = (event: Record<string, unknown> | null, extra?: Record<string, unknown>) => ({
  current_phase: 'INDEPENDENT_PRACTICE',
  question_id: null,
  current_question: null,
  student_model_event: event,
  ...extra,
} as unknown as Parameters<typeof syncBackendSession>[0]);

const REQUEST = { intervention_id: 'INT-T03-001', prompt: 'What are you finding difficult?' };

describe('intervention stage from the reply', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      interventionStage: 'NONE',
      interventionRequest: null,
      currentPhase: 'INDEPENDENT_PRACTICE',
    });
  });

  it('TC-33: opens the popup and keeps the backend’s own content', () => {
    syncBackendSession(reply({
      phase_payload: { payload_type: 'INTERVENTION_INPUT_REQUIRED', intervention_input_request: REQUEST },
    }));
    expect(state().interventionStage).toBe('COLLECTING');
    expect(state().interventionRequest).toEqual(REQUEST);
  });

  it('TC-36: the reply to a submission pauses rather than reopening', () => {
    state().setInterventionState({ stage: 'COLLECTING', request: REQUEST });
    syncBackendSession(reply(
      {
        phase_payload: null,
        routing: { next_action: 'AWAIT_INTERVENTION_REVIEW' },
        status: { intervention_required: true },
      },
      { routing: { next_action: 'AWAIT_INTERVENTION_REVIEW' } },
    ));
    expect(state().interventionStage).toBe('AWAITING_REVIEW');
    expect(state().interventionRequest).toBeNull();
  });

  it('an ordinary turn does NOT take the popup down', () => {
    state().setInterventionState({ stage: 'COLLECTING', request: REQUEST });
    syncBackendSession(reply({ phase_payload: { payload_type: 'QUESTION_SET' } }));
    expect(state().interventionStage).toBe('COLLECTING');
  });

  it('a reply with no student model event at all does not take it down either', () => {
    state().setInterventionState({ stage: 'AWAITING_REVIEW' });
    syncBackendSession(reply(null));
    expect(state().interventionStage).toBe('AWAITING_REVIEW');
  });

  it('the backend routing the student back to work is what clears it', () => {
    state().setInterventionState({ stage: 'AWAITING_REVIEW' });
    syncBackendSession(reply({ phase_payload: { payload_type: 'FRESH_INDEPENDENT_QUESTION' } }));
    expect(state().interventionStage).toBe('NONE');
  });
});
