import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SessionRecord } from '@/lib/api';

const startSession = vi.fn();
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  startSession: (...args: unknown[]) => startSession(...args),
}));
vi.mock('@/lib/tts', () => ({ speakTutor: vi.fn(), stopTutorSpeech: vi.fn() }));
vi.mock('@/components/CenteredScreen', () => ({ CenteredScreen: () => null, ScreenIcon: () => null }));
vi.mock('@/components/ScreenMarks', () => ({
  CelebrationMark: () => null,
  PlacementMark: () => null,
  ProblemMark: () => null,
}));
vi.mock('next/navigation', () => ({
  notFound: vi.fn(),
  useRouter: () => ({ push: vi.fn() }),
}));

const DIAGNOSTIC = {
  session_id: 'SESSION-T02',
  current_phase: 'DIAGNOSTIC',
  current_question: 'What does 4y mean?',
  question_id: 'Q-T02-D01',
  student_model_event: {
    phase_payload: {
      question_set: {
        questions: [{
          question_id: 'Q-T02-D01',
          student_view: {
            question_text: 'What does 4y mean?',
            question_type: 'SINGLE_CHOICE',
            options: [
              { option_id: 'A', text: '4 + y' },
              { option_id: 'B', text: '4 times y' },
            ],
            requires_student_response: true,
          },
        }],
      },
    },
  },
} as unknown as SessionRecord;

describe('topic diagnostic session start', () => {
  let root: Root;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    startSession.mockReset();
    startSession.mockResolvedValue(DIAGNOSTIC);
  });

  afterEach(async () => {
    await act(async () => root?.unmount());
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    vi.resetModules();
  });

  it('starts the topic named by the diagnostic route when persisted handoff state is absent', async () => {
    const { default: DiagnosticClient } = await import('@/app/topic-diagnostic/DiagnosticClient');
    const { useNumeraStore } = await import('@/store/useNumeraStore');
    useNumeraStore.setState({
      sessionId: null,
      backendSession: null,
      activeConceptId: 'ALG-KS3-01',
      pendingTopicCode: null,
    });

    root = createRoot(document.createElement('div'));
    await act(async () => root.render(createElement(DiagnosticClient, { topicId: 'ALG-ORI-02' })));

    expect(startSession).toHaveBeenCalledWith({
      student_id: expect.any(String),
      topic_code: 'ALG-ORI-02',
      interaction_mode: 'TEXT',
    });
  });
});
