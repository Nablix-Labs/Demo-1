import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const submitCanvas = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  submitCanvas: (...args: unknown[]) => submitCanvas(...args),
}));
vi.mock('@/lib/tutorSpeech', () => ({
  setStudentWriting: vi.fn(),
  tutorSay: vi.fn(),
}));

import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

describe('Canvas phase synchronization', () => {
  let root: Root;
  let tutor: ReturnType<typeof useDemoTutor> | null;

  beforeEach(async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    submitCanvas.mockReset();
    tutor = null;
    useNumeraStore.setState({
      sessionId: 'SESSION001',
      currentPhase: 'INDEPENDENT_PRACTICE',
      activeQuestionId: 'Q-T01-007',
      questionText: 'Write the general rule.',
      items: [
        {
          id: 'stroke-1',
          kind: 'stroke',
          tool: 'pen',
          points: [0, 0, 1, 1],
          color: '#000000',
          size: 3,
        },
      ],
      canvasExporter: () => ({
        snapshotDataUrl: 'data:image/png;base64,c25hcHNob3Q=',
        strokes: [],
        capturedAt: '2026-08-11T10:29:28.000Z',
      }),
    });
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

  it('applies Review when a successful Canvas response clears the question', async () => {
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001',
      student_id: 'ST001',
      status: 'processed',
      submission_id: 'SUBMISSION001',
      snapshot_reference: 'snapshot://SUBMISSION001',
      current_phase: 'REVIEW',
      current_question: null,
      question_id: null,
      phase_changed: true,
      previous_phase: 'INDEPENDENT_PRACTICE',
      ocr: {
        raw_ocr_text: 't - 3',
        detected_equation: 't - 3',
        detected_steps: [],
        detected_regions: [],
        confidence: 0.99,
        needs_clarification: false,
      },
      tutor: {
        evaluation: 'CORRECT',
        tutor_message: 'Correct.',
        tutor_message_voice: 'Correct.',
      },
      latency: {
        ocr_latency_ms: 1,
        tutor_latency_ms: 1,
        total_latency_ms: 2,
      },
    });

    await act(async () => {
      await tutor?.submitCanvasWork();
    });

    const state = useNumeraStore.getState();
    expect(state.currentPhase).toBe('REVIEW');
    expect(state.activeQuestionId).toBeNull();
    expect(state.questionText).toBe('');
  });

  /**
   * Independent Practice REJECTS a canvas submission with no turn_id.
   *
   * canvas_service.py:130 answers 422 "turn_id is required for Independent
   * Practice Canvas submissions" (Chiru, 12 Aug 2026), so every Phase 3 canvas
   * submission was failing before it reached OCR. The id is also the backend's
   * dedupe key, which is why it must look like a real minted turn rather than
   * any placeholder string.
   */
  it('sends a minted turn id with every canvas submission', async () => {
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001', student_id: 'ST001', status: 'processed',
      submission_id: 'SUBMISSION002', snapshot_reference: 'snapshot://SUBMISSION002',
      ocr: null, tutor: null,
      latency: { ocr_latency_ms: 1, tutor_latency_ms: 1, total_latency_ms: 2 },
    });

    await act(async () => { await tutor?.submitCanvasWork(); });

    expect(submitCanvas).toHaveBeenCalledTimes(1);
    const [, , submissionRole, turnId] = submitCanvas.mock.calls[0];
    expect(submissionRole).toBe('STANDALONE_ATTEMPT');
    expect(turnId).toMatch(/^TURN-/);
  });

  it('gives each submission its own turn id', async () => {
    // Two submissions are two attempts. Reusing one id would make the backend
    // treat the second as a duplicate of the first and discard the new work.
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001', student_id: 'ST001', status: 'processed',
      submission_id: 'S', snapshot_reference: 'snapshot://S',
      ocr: null, tutor: null,
      latency: { ocr_latency_ms: 1, tutor_latency_ms: 1, total_latency_ms: 2 },
    });

    await act(async () => { await tutor?.submitCanvasWork(); });
    await act(async () => { await tutor?.submitCanvasWork(); });

    const [first, second] = submitCanvas.mock.calls.map((call) => call[3]);
    expect(first).toMatch(/^TURN-/);
    expect(second).toMatch(/^TURN-/);
    expect(first).not.toBe(second);
  });

  it('does not throw when Phase 3 returns no OCR and no tutor block', async () => {
    // The live Phase 3 shape: accepted, graded, and silent. Reading through
    // either field threw and reported accepted work as a failure.
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001', student_id: 'ST001', status: 'processed',
      submission_id: 'S3', snapshot_reference: 'snapshot://S3',
      ocr: null, tutor: null,
      independent_outcome: 'RESCUE_REQUIRED', independent_attempt_terminal: true,
      latency: { ocr_latency_ms: 1, tutor_latency_ms: 1, total_latency_ms: 2 },
    });

    let result: unknown = 'not set';
    await act(async () => { result = await tutor?.submitCanvasWork(); });
    expect(result).not.toBeNull();
  });
});
