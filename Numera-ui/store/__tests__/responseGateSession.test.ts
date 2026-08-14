import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';
import { noteApplied, shouldApply, EMPTY_APPLIED } from '@/lib/responseGate';

/**
 * The ordering guard must not survive a session boundary.
 *
 * `interaction_state_version` is monotonic WITHIN a session, so a new session
 * starts counting from the bottom again. Carrying the previous session's
 * high-water mark forward would make every reply in the new session look stale
 * and be dropped — the lesson would open and then never respond to anything.
 */
beforeEach(() => {
  useNumeraStore.setState({ appliedResponse: EMPTY_APPLIED, sessionId: null });
});

describe('the ordering guard resets with the session', () => {
  it('a new session accepts low version numbers again', () => {
    const store = useNumeraStore.getState();
    store.setAppliedResponse(
      noteApplied({ interaction_state_version: 57, accepted_turn_id: 'old' }, EMPTY_APPLIED),
    );
    expect(useNumeraStore.getState().appliedResponse.version).toBe(57);

    useNumeraStore.getState().setSessionId('SESSION_NEW');

    const applied = useNumeraStore.getState().appliedResponse;
    expect(applied).toEqual(EMPTY_APPLIED);
    // Version 1 of the new session must be accepted, not judged against 57.
    expect(shouldApply({ interaction_state_version: 1, accepted_turn_id: 't1' }, applied)).toBe(true);
  });

  it('ending a session clears it too', () => {
    useNumeraStore
      .getState()
      .setAppliedResponse(
        noteApplied({ interaction_state_version: 12, accepted_turn_id: 'x' }, EMPTY_APPLIED),
      );
    useNumeraStore.getState().clearSessionId();
    expect(useNumeraStore.getState().appliedResponse).toEqual(EMPTY_APPLIED);
  });

  it('is never written to localStorage', () => {
    // It describes what is on screen right now, not the lesson. A version
    // restored from yesterday would block today's first reply.
    const persisted = localStorage.getItem('numera-store');
    if (persisted) expect(persisted).not.toContain('appliedResponse');
  });
});
