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

import { useDemoTutor, syncBackendSession } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

const contentGap = () => Object.assign(new Error('CONTENT_GAP'), {
  response: { status: 409, data: { error_code: 'CONTENT_GAP', message: '' } },
});

/**
 * The ST017 retry loop, made impossible.
 *
 * The only authored Independent question for T01.M7 had already been used. With
 * nothing on this side saying "stop", the client asked for a fresh one twice —
 * journey versions 12 then 13. The backend now persists the pause on the first
 * authoritative gap response; these tests are the client half of that.
 */
describe('a topic paused on a content gap', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  beforeEach(async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    submitCanvas.mockReset();
    getSession.mockReset();
    tutor = null;
    useNumeraStore.setState({
      sessionId: 'SESSION001',
      activeConceptId: 'T01',
      currentPhase: 'INDEPENDENT_PRACTICE',
      activeQuestionId: 'Q-T01-009',
      sessionRecovering: false,
      contentGapPaused: false,
      transcript: [],
      backendSession: null,
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

  it('raises the pause when a submission is refused', async () => {
    submitCanvas.mockRejectedValueOnce(contentGap());

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(useNumeraStore.getState().contentGapPaused).toBe(true);
  });

  it('does not submit again once paused', async () => {
    submitCanvas.mockRejectedValueOnce(contentGap());
    await act(async () => { await tutor?.submitCanvasWork(); });
    expect(submitCanvas).toHaveBeenCalledTimes(1);

    // Ink back on the canvas, so the second press is stopped by the pause and
    // not by an empty board.
    useNumeraStore.setState({
      items: [{
        id: 'stroke-2', kind: 'stroke', tool: 'pen',
        points: [2, 2, 3, 3], color: '#000000', size: 3,
      }],
    } as never);

    await act(async () => { await tutor?.submitCanvasWork(); });
    expect(submitCanvas).toHaveBeenCalledTimes(1);
  });

  it('does not recover a gap as if it were a conflict', async () => {
    // A gap is not stale state. Reading the session to "fix" it would be the
    // second request the persisted pause exists to prevent.
    submitCanvas.mockRejectedValueOnce(contentGap());

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(getSession).not.toHaveBeenCalled();
    expect(useNumeraStore.getState().sessionRecovering).toBe(false);
  });

  it('lifts the pause when the backend serves a question again', async () => {
    useNumeraStore.setState({ contentGapPaused: true } as never);

    await act(async () => {
      syncBackendSession({
        session_id: 'SESSION001',
        concept_id: 'T01',
        current_phase: 'INDEPENDENT_PRACTICE',
        current_question: 'Write the general rule.',
        question_id: 'Q-T01-010',
        student_model_event: { routing: { content_gap_detected: false } },
      } as never);
    });

    expect(useNumeraStore.getState().contentGapPaused).toBe(false);
  });
});
