import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

describe('student turn identity', () => {
  beforeEach(() => {
    useNumeraStore.setState({ currentTurnId: null });
  });

  it('creates globally unique idempotency keys instead of reload-local sequence numbers', () => {
    const ids = Array.from(
      { length: 100 },
      () => useNumeraStore.getState().beginSubmissionTurn(),
    );

    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.every((id) => id.startsWith('TURN-'))).toBe(true);
    expect(ids).not.toContain('TURN-0001');
  });
});
