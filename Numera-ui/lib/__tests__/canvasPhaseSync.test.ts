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
});
