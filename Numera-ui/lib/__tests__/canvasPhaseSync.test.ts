import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const submitCanvas = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  submitCanvas: (...args: unknown[]) => submitCanvas(...args),
}));
// Only the two that reach a speech engine are stubbed. The rest of the module
// is kept real so it cannot go stale: the voice-floor helpers no-op while
// `voiceStatus` is 'idle', which is what these tests run in.
vi.mock('@/lib/tutorSpeech', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/tutorSpeech')>()),
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

  /**
   * Rows 24 and 55 — "question options are not shown in phase 3", reported on
   * 11 Aug and again on 26 Aug.
   *
   * Options never travel on a reply; they are looked up out of the cached
   * session record by question id. /canvas/submit is the path a student
   * actually LEAVES Phase 2 by — they press "Check my work" and the backend
   * moves them to Independent Practice with a new question set — and this
   * handler used to pass syncBackendSession three hand-picked fields off the
   * response. student_model_event was not among them, so the record kept
   * PHASE 2's questions, the new question id was not in them, and Phase 3
   * opened with questionType null and no options at all.
   */
  it('carries the new phase\'s question set, so Phase 3 has its options', async () => {
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-T01-004',
      questionType: null,
      questionOptions: [],
      backendSession: {
        session_id: 'SESSION001',
        student_model_event: {
          phase_payload: {
            question_set: {
              questions: [{ question_id: 'Q-T01-004', student_view: {
                question_text: 'Write the general rule.',
                question_type: 'SHORT_RESPONSE',
                options: [],
              } }],
            },
          },
        },
      } as never,
    });
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001',
      student_id: 'ST001',
      status: 'processed',
      submission_id: 'SUBMISSION002',
      snapshot_reference: 'snapshot://SUBMISSION002',
      current_phase: 'INDEPENDENT_PRACTICE',
      current_question: 'Which is the general rule?',
      question_id: 'Q-T01-009',
      question_type: 'SINGLE_CHOICE',
      phase_changed: true,
      previous_phase: 'GUIDED_PRACTICE',
      ocr: null,
      tutor: null,
      // The new phase's set rides on the reply, exactly as it does on
      // /interaction. Nothing read it here.
      student_model_event: {
        phase_payload: {
          question_set: {
            questions: [{ question_id: 'Q-T01-009', student_view: {
              question_text: 'Which is the general rule?',
              question_type: 'SINGLE_CHOICE',
              options: [
                { option_id: 'A', text: 'n + 4' },
                { option_id: 'B', text: '3 + 4' },
              ],
            } }],
          },
        },
      },
    });

    await act(async () => { await tutor?.submitCanvasWork(); });

    const state = useNumeraStore.getState();
    expect(state.activeQuestionId).toBe('Q-T01-009');
    expect(state.questionType).toBe('SINGLE_CHOICE');
    expect(state.questionOptions.map((o) => o.option_id)).toEqual(['A', 'B']);
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

  it('applies Guided canvas actions and records the canvas tutor turn immediately', async () => {
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-T01-002',
      questionText: 'In m + 7, identify the changing quantity.',
    });
    submitCanvas.mockResolvedValue({
      session_id: 'SESSION001', student_id: 'ST001', status: 'processed',
      submission_id: 'S-ACTION', snapshot_reference: 'snapshot://S-ACTION',
      current_phase: 'GUIDED_PRACTICE',
      current_question: 'In m + 7, identify the changing quantity.',
      question_id: 'Q-T01-002',
      message: 'I can see that 7 stays fixed. What does m do?',
      tutor_turn_id: 'TUTOR-CANVAS-1',
      expected_student_response: 'ANSWER',
      allow_voice_input: true,
      tutor_canvas_actions: [{
        action_id: 'CANVAS-CONFIRM-1',
        type: 'INSERT_LABEL',
        target_kind: 'TUTOR_ANCHOR',
        target_object_id: 'TUTOR_ANCHOR:CONFIRMED:Q-T01-002:1',
        confirmed_component_id: 'FIXED_VALUE',
        text: '7 → stays fixed',
        source_id: null,
        answer_reveal_allowed: false,
      }],
      ocr: null,
      tutor: { evaluation: 'PARTIAL', tutor_message: 'I can see that 7 stays fixed.' },
      latency: { ocr_latency_ms: 1, tutor_latency_ms: 1, total_latency_ms: 2 },
    });

    await act(async () => { await tutor?.submitCanvasWork(); });

    const state = useNumeraStore.getState();
    expect(state.lastTutorTurnId).toBe('TUTOR-CANVAS-1');
    expect(state.expectsStudentResponse).toBe(true);
    expect(state.tutorElements.some((element) => element.text === '7 → stays fixed')).toBe(true);
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
