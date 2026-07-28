/**
 * Session-start de-duplication.
 *
 * The failure this prevents actually happened on 2026-07-28: a screen that
 * opened a session on mount was remounted in a loop (AuthGate swaps `children`
 * for a spinner on any auth-store change), firing ~4,500 POST /session/start in
 * under two minutes. That exhausted the backend's in-memory SESSION001–SESSION999
 * range, after which EVERY request 500'd until the service was restarted — so
 * one frontend bug took down the shared dev backend for everyone.
 *
 * A component ref can't guard this because it doesn't survive a remount. The
 * guard lives at module scope in useDemoTutor, which is what these tests pin.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const startSession = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  startSession: (...args: unknown[]) => startSession(...args),
}));
vi.mock('@/lib/tts', () => ({ speakTutor: vi.fn() }));

const RECORD = {
  session_id: 'SESSION001',
  current_phase: 'DIAGNOSTIC',
  current_question: 'What does 4y mean?',
  question_id: 'Q-T02-D01',
};

/** Fresh module state per test — the guard is module-level by design. */
async function loadTutor() {
  vi.resetModules();
  process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
  const { beginSession, resetSessionStart } = await import('@/hooks/useDemoTutor');
  const { useNumeraStore } = await import('@/store/useNumeraStore');
  useNumeraStore.setState({ sessionId: null, backendSession: null });
  return { beginSession, resetSessionStart, useNumeraStore };
}

describe('session start', () => {
  beforeEach(() => { startSession.mockReset(); });
  afterEach(() => { delete process.env.NEXT_PUBLIC_API_BASE_URL; });

  it('collapses a burst of concurrent starts into ONE request', async () => {
    startSession.mockResolvedValue(RECORD);
    const { beginSession } = await loadTutor();
    await Promise.all(Array.from({ length: 50 }, () => beginSession('ALG_LINEAR_ONE_STEP')));
    expect(startSession).toHaveBeenCalledTimes(1);
  });

  it('does not open a second session once one exists', async () => {
    startSession.mockResolvedValue(RECORD);
    const { beginSession } = await loadTutor();
    await beginSession('ALG_LINEAR_ONE_STEP');
    await beginSession('ALG_LINEAR_ONE_STEP');
    await beginSession('ALG_LINEAR_ONE_STEP');
    expect(startSession).toHaveBeenCalledTimes(1);
  });

  it('stops retrying after a failure instead of hammering the endpoint', async () => {
    startSession.mockRejectedValue(new Error('boom'));
    const { beginSession } = await loadTutor();
    for (let i = 0; i < 20; i++) expect(await beginSession('ALG_LINEAR_ONE_STEP')).toBeNull();
    expect(startSession).toHaveBeenCalledTimes(1);
  });

  it('lets an explicit retry try again', async () => {
    startSession.mockRejectedValueOnce(new Error('boom')).mockResolvedValue(RECORD);
    const { beginSession, resetSessionStart } = await loadTutor();
    expect(await beginSession('ALG_LINEAR_ONE_STEP')).toBeNull();
    resetSessionStart();
    expect(await beginSession('ALG_LINEAR_ONE_STEP')).toEqual(RECORD);
    expect(startSession).toHaveBeenCalledTimes(2);
  });
});
