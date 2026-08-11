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
const getSession = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  startSession: (...args: unknown[]) => startSession(...args),
  getSession: (...args: unknown[]) => getSession(...args),
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
  const { beginSession, recoverIfStaleSession, resetSessionStart, resumeSession } = await import('@/hooks/useDemoTutor');
  const { useNumeraStore } = await import('@/store/useNumeraStore');
  useNumeraStore.setState({ sessionId: null, backendSession: null });
  return { beginSession, recoverIfStaleSession, resetSessionStart, resumeSession, useNumeraStore };
}

describe('session start', () => {
  beforeEach(() => {
    startSession.mockReset();
    getSession.mockReset();
  });
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

  it('drops a backend-forgotten session so the lesson can restart', async () => {
    const { recoverIfStaleSession, useNumeraStore } = await loadTutor();
    useNumeraStore.setState({ sessionId: 'SESSION-FORGOTTEN', backendSession: RECORD });

    const recovered = recoverIfStaleSession({
      response: {
        status: 404,
        data: { message: 'Session with ID SESSION-FORGOTTEN was not found.' },
      },
    });

    expect(recovered).toBe(true);
    expect(useNumeraStore.getState().sessionId).toBeNull();
    expect(useNumeraStore.getState().backendSession).toBeNull();
  });

  it('restores the complete tutor-turn contract after a refresh', async () => {
    getSession.mockResolvedValue({
      ...RECORD,
      question_number: 3,
      message: 'What operation connects the changing value and five?',
      conversation_history: [
        { role: 'assistant', content: 'Write the general rule.' },
        { role: 'user', content: 'n + 5' },
        { role: 'assistant', content: 'Why does n make it general?' },
      ],
      last_tutor_turn_id: 'TUTOR-RESTORED',
      expected_student_response: 'ANSWER',
      allow_voice_input: true,
      inactivity_policy: {
        initial_idle_threshold_ms: 45000,
        cooldown_ms: 30000,
        max_nudges_per_tutor_turn: 2,
        generated_nudge_rate_limit: 2,
      },
    });
    const { resumeSession, useNumeraStore } = await loadTutor();
    useNumeraStore.setState({ sessionId: 'SESSION001', backendSession: null, transcript: [] });

    await resumeSession();

    const state = useNumeraStore.getState();
    expect(state.questionNumber).toBe(3);
    expect(state.lastTutorTurnId).toBe('TUTOR-RESTORED');
    expect(state.expectsStudentResponse).toBe(true);
    expect(state.allowVoiceInput).toBe(true);
    expect(state.inactivityPolicy?.initialIdleThresholdMs).toBe(45000);
    expect(state.transcript.map(({ role, text }) => ({ role, text }))).toEqual([
      { role: 'ai', text: 'Write the general rule.' },
      { role: 'student', text: 'n + 5' },
      { role: 'ai', text: 'Why does n make it general?' },
    ]);
  });
});
