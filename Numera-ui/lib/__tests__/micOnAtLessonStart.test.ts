/**
 * Manjusha, 4 Oct: after picking an option the tutor said "Now say or write
 * why you picked it" and the mic was still muted — "this is not enabled
 * automatically". A new lesson now opens with the mic on; the half-duplex gate
 * still keeps it shut while the tutor speaks.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '/api');

vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  startSession: vi.fn(async () => ({ session_id: 'S-NEW', concept_id: null, current_question: null })),
}));

import { beginSession } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

describe('the mic at lesson start', () => {
  beforeEach(() => {
    useNumeraStore.getState().reset();
  });

  it('comes on when a new session opens, even if it was muted before', async () => {
    useNumeraStore.getState().setMicMuted(true);
    await beginSession('ALG_LINEAR_ONE_STEP', 'VOICE');
    expect(useNumeraStore.getState().sessionId).toBe('S-NEW');
    expect(useNumeraStore.getState().micMuted).toBe(false);
  });
});
