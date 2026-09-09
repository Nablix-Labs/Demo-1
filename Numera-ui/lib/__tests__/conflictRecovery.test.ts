import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const submitCanvas = vi.fn();
const getSession = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  submitCanvas: (...args: unknown[]) => submitCanvas(...args),
  getSession: (...args: unknown[]) => getSession(...args),
}));
vi.mock('@/lib/tutorSpeech', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/tutorSpeech')>()),
  setStudentWriting: vi.fn(),
  tutorSay: vi.fn(),
}));

import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

const conflict = (error_code = 'JOURNEY_VERSION_CONFLICT') => Object.assign(
  new Error(error_code),
  { response: { status: 409, data: { error_code, message: '' } } },
);

/** The session GET returns whatever question the backend says is authoritative. */
const recovered = (question_id: string | null, over: Record<string, unknown> = {}) => ({
  session_id: 'SESSION001',
  student_id: 'ST010',
  concept_id: 'T01',
  current_phase: 'INDEPENDENT_PRACTICE',
  current_question: 'Write the general rule.',
  question_id,
  question_number: 3,
  ...over,
});

/**
 * The ST010 corruption, in one file.
 *
 * The live sequence was: 503 after Student Model had already accepted a failed
 * checkpoint, then a journey-version conflict, then the student's ink for the
 * OLD question submitted against a newly selected one. The last step is what
 * corrupted evidence, and every test here exists to keep it impossible.
 */
describe('recovery after a journey conflict', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  const mount = async () => {
    const container = document.createElement('div');
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(() => {
        tutor = useDemoTutor();
        return null;
      }));
    });
  };

  beforeEach(async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    submitCanvas.mockReset();
    getSession.mockReset();
    tutor = null;
    useNumeraStore.setState({
      sessionId: 'SESSION001',
      activeConceptId: 'T01',
      currentPhase: 'INDEPENDENT_PRACTICE',
      activeQuestionId: 'Q-T01-003',
      questionText: 'Write the general rule.',
      sessionRecovering: false,
      transcript: [],
      items: [{
        id: 'stroke-1', kind: 'stroke', tool: 'pen',
        points: [0, 0, 1, 1], color: '#000000', size: 3,
      }],
      canvasExporter: () => ({
        snapshotDataUrl: 'data:image/png;base64,c25hcHNob3Q=',
        strokes: [],
        capturedAt: '2026-09-09T10:00:00.000Z',
      }),
    } as never);
    await mount();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it('reads the session once, rather than re-POSTing the submission', async () => {
    // The re-POST is refused with SESSION_STATE_REFRESH_REQUIRED, so a retry
    // here would spend the student's attempt on a guaranteed refusal.
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockResolvedValueOnce(recovered('Q-T01-003'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(submitCanvas).toHaveBeenCalledTimes(1);
    expect(getSession).toHaveBeenCalledTimes(1);
  });

  it('re-opens Check when recovery returns the same question', async () => {
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockResolvedValueOnce(recovered('Q-T01-003'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().sessionRecovering).toBe(false);
  });

  it('keeps Check shut when recovery returns a different question', async () => {
    // This is the corrupting case. The ink on the canvas answers Q-T01-003; the
    // authoritative question is now Q-T01-004, and submitting would grade that
    // ink against a question the student never saw.
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockResolvedValueOnce(recovered('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().sessionRecovering).toBe(true);
  });

  it('does not submit again while recovery is unresolved', async () => {
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockResolvedValueOnce(recovered('Q-T01-004'));
    await act(async () => { await tutor?.submitCanvasWork(); });
    expect(submitCanvas).toHaveBeenCalledTimes(1);
    expect(useNumeraStore.getState().sessionRecovering).toBe(true);

    // Put ink back on the canvas. Recovery cleared it along with the stale
    // question, and without this the second press would bail on an empty
    // canvas — passing the test while proving nothing about the gate.
    useNumeraStore.setState({
      items: [{
        id: 'stroke-2', kind: 'stroke', tool: 'pen',
        points: [2, 2, 3, 3], color: '#000000', size: 3,
      }],
    } as never);

    // A second press of Check must not reach the network at all.
    await act(async () => { await tutor?.submitCanvasWork(); });
    expect(submitCanvas).toHaveBeenCalledTimes(1);
  });

  it('leaves Check shut when the recovering read itself fails', async () => {
    // Not knowing which question is authoritative is exactly the state in which
    // submitting is unsafe. Failing open would restore the ST010 bug.
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockRejectedValueOnce(new Error('Network Error'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().sessionRecovering).toBe(true);
  });

  it('recovers from the refusal code as well as from the conflict itself', async () => {
    submitCanvas.mockRejectedValueOnce(conflict('SESSION_STATE_REFRESH_REQUIRED'));
    getSession.mockResolvedValueOnce(recovered('Q-T01-003'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(useNumeraStore.getState().sessionRecovering).toBe(false);
  });

  it('tells the student the work is safe, without asking for a resubmit', async () => {
    submitCanvas.mockRejectedValueOnce(conflict());
    getSession.mockResolvedValueOnce(recovered('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    const said = useNumeraStore.getState().transcript.filter((m) => m.role === 'ai');
    expect(said.some((m) => /safe/i.test(m.text))).toBe(true);
    expect(said.some((m) => /press check|try again|once more/i.test(m.text))).toBe(false);
  });

  it('does not recover an intervention pause as if it were a conflict', async () => {
    // A pause has its own screen and its own read. Recovering it here would
    // re-open Check on a topic that is closed to learning actions.
    submitCanvas.mockRejectedValueOnce(conflict('INTERVENTION_REQUIRED'));
    getSession.mockResolvedValue(recovered('Q-T01-003'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().sessionRecovering).toBe(false);
  });
});
