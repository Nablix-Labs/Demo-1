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

const httpError = (status: number, error_code = '') => Object.assign(
  new Error(String(status)),
  { response: { status, data: { error_code, message: '' } } },
);

const record = (question_id: string | null) => ({
  session_id: 'SESSION001',
  student_id: 'ST010',
  concept_id: 'T01',
  current_phase: 'INDEPENDENT_PRACTICE',
  current_question: 'Write the general rule.',
  question_id,
  question_number: 3,
});

/**
 * The student's ink belongs to the question it answers.
 *
 * The ST010 corruption was old-question ink submitted against a newly selected
 * question. Dropping ink too eagerly is the opposite failure and just as real:
 * a 503 is an UNCERTAIN outcome, not a rejection, and erasing on one throws
 * away work the student may still need. So the rule is asymmetric — keep it
 * while the question is unchanged, drop it from the submission buffer when the
 * question moves.
 */
describe('ink lifecycle across a failed submission', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  const ink = (id: string) => ({
    id, kind: 'stroke', tool: 'pen',
    points: [0, 0, 1, 1], color: '#000000', size: 3,
  });

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
      items: [ink('stroke-1')],
      canvasExporter: () => ({
        snapshotDataUrl: 'data:image/png;base64,c25hcHNob3Q=',
        strokes: [],
        capturedAt: '2026-09-09T10:00:00.000Z',
      }),
    } as never);
    const container = document.createElement('div');
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(() => {
        tutor = useDemoTutor();
        return null;
      }));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it('keeps the work when a 503 leaves the outcome uncertain', async () => {
    // Student Model may already have committed the attempt. Erasing here would
    // destroy work on a submission that might well have landed.
    submitCanvas.mockRejectedValueOnce(httpError(503));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().items).toHaveLength(1);
  });

  it('keeps the work when recovery returns the same question', async () => {
    submitCanvas.mockRejectedValueOnce(httpError(409, 'JOURNEY_VERSION_CONFLICT'));
    getSession.mockResolvedValueOnce(record('Q-T01-003'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().activeQuestionId).toBe('Q-T01-003');
    expect(useNumeraStore.getState().items).toHaveLength(1);
  });

  it('drops the work from the submission buffer when the question changed', async () => {
    // Never relabelled, never replayed under a new turn id. The ink answered
    // Q-T01-003 and there is no honest way to offer it as an answer to -004.
    submitCanvas.mockRejectedValueOnce(httpError(409, 'JOURNEY_VERSION_CONFLICT'));
    getSession.mockResolvedValueOnce(record('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().activeQuestionId).toBe('Q-T01-004');
    expect(useNumeraStore.getState().items).toHaveLength(0);
  });

  it('drops the question-scoped canvas events with it', async () => {
    // canvas_events carry their own question_id. Sent against a new question
    // they are what the backend rejects as STALE_CANVAS_EVENTS — and if it did
    // not, they would be memory of the wrong problem.
    useNumeraStore.setState({
      canvasEvents: [{ question_id: 'Q-T01-003', turn_id: 'T1' }],
    } as never);
    submitCanvas.mockRejectedValueOnce(httpError(409, 'JOURNEY_VERSION_CONFLICT'));
    getSession.mockResolvedValueOnce(record('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().canvasEvents).toHaveLength(0);
  });
});

/**
 * A canvas submission rejected for carrying the previous question's events.
 *
 * The backend guard is correct and stays: `canvas_events_are_stale` compares
 * every event's question id against the session's, and it is what stopped the
 * corrupted submission in the live run. It answers 200 STALE_TURN — NOT a 409,
 * despite the handoff describing it as one — so it arrives as a response to be
 * read, not an error to be caught.
 *
 * What the client owed it was a re-sync: being told our canvas identity is
 * stale means the question on screen is not the authoritative one, and only a
 * read can say what is.
 */
describe('a stale-canvas-events rejection', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  const staleTurn = {
    status: 'STALE_TURN',
    accepted_turn_id: null,
    expected_previous_tutor_turn_id: 'TUTOR-1',
    conversation_action: 'WAIT_FOR_STUDENT',
    attempt_increment: 0,
    retry_safe: false,
    message: 'That turn is no longer current.',
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
    const container = document.createElement('div');
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(() => {
        tutor = useDemoTutor();
        return null;
      }));
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it('reads the session so the displayed question stops being stale', async () => {
    submitCanvas.mockResolvedValueOnce(staleTurn);
    getSession.mockResolvedValueOnce(record('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(getSession).toHaveBeenCalledTimes(1);
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q-T01-004');
  });

  it('does not retry the submission', async () => {
    // retry_safe is false on a stale turn. Resending would be the corrupting
    // submission all over again, this time with our own encouragement.
    submitCanvas.mockResolvedValueOnce(staleTurn);
    getSession.mockResolvedValueOnce(record('Q-T01-004'));

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(submitCanvas).toHaveBeenCalledTimes(1);
  });
});
