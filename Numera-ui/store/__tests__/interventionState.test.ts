/**
 * The intervention pause, as a state rather than as an inference.
 *
 * Both cases here are ones an "is there a request?" check gets wrong, and both
 * are live per Chirudeva's 7 Sep handoff: the request arrives once and then
 * disappears, while the pause outlives it.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const REQUEST = {
  intervention_id: 'INT-T03-001',
  prompt: 'What are you finding difficult?',
  selection_required: true,
};

describe('intervention state', () => {
  beforeEach(() => {
    useNumeraStore.setState({ interventionStage: 'NONE', interventionRequest: null });
  });

  it('holds the request while collecting', () => {
    useNumeraStore.getState().setInterventionState({ stage: 'COLLECTING', request: REQUEST });
    expect(useNumeraStore.getState().interventionStage).toBe('COLLECTING');
    expect(useNumeraStore.getState().interventionRequest).toEqual(REQUEST);
  });

  it('collects even when the request is missing — the topic can be paused by status alone', () => {
    useNumeraStore.getState().setInterventionState({ stage: 'COLLECTING', request: null });
    expect(useNumeraStore.getState().interventionStage).toBe('COLLECTING');
  });

  it('drops the request once the input is in, so a stale case id cannot be resubmitted', () => {
    useNumeraStore.getState().setInterventionState({ stage: 'COLLECTING', request: REQUEST });
    useNumeraStore.getState().setInterventionState({ stage: 'AWAITING_REVIEW' });
    expect(useNumeraStore.getState().interventionRequest).toBeNull();
    expect(useNumeraStore.getState().interventionStage).toBe('AWAITING_REVIEW');
  });

  it('a new session leaves no pause behind', () => {
    useNumeraStore.getState().setInterventionState({ stage: 'COLLECTING', request: REQUEST });
    useNumeraStore.getState().setSessionId('S-2');
    expect(useNumeraStore.getState().interventionStage).toBe('NONE');
    expect(useNumeraStore.getState().interventionRequest).toBeNull();
  });
});
