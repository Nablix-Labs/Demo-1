import { beforeEach, describe, expect, it } from 'vitest';
import { syncBackendSession } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';

/**
 * A reply that lands after the student has moved on must not be applied.
 *
 * The topic transition is the case that matters. Review completes, the client
 * opens Topic 2, and an in-flight reply for Topic 1 arrives afterwards. It
 * carries a real phase and a real question, so every guard downstream reads it
 * as legitimate — and applying it puts the student back on a topic they have
 * finished, holding a question they already answered.
 *
 * `syncBackendSession` is the single place a backend phase update is applied,
 * which is why the check lives there and is tested through it.
 */
describe('late responses from a superseded session or topic', () => {
  const reply = (over: Record<string, unknown> = {}) => ({
    current_phase: 'INDEPENDENT_PRACTICE',
    current_question: 'Write the general rule.',
    question_id: 'Q-T02-001',
    ...over,
  });

  beforeEach(() => {
    useNumeraStore.setState({
      sessionId: 'SESSION002',
      activeConceptId: 'T02',
      currentPhase: 'ORIENTATION',
      activeQuestionId: null,
      questionText: '',
    } as never);
  });

  it('applies a reply from the active session and topic', () => {
    syncBackendSession(reply({ session_id: 'SESSION002', concept_id: 'T02' }));
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q-T02-001');
  });

  it('drops a reply from the session the student has left', () => {
    syncBackendSession(reply({
      session_id: 'SESSION001', concept_id: 'T02', question_id: 'Q-T01-009',
    }));
    expect(useNumeraStore.getState().activeQuestionId).toBeNull();
    expect(useNumeraStore.getState().currentPhase).toBe('ORIENTATION');
  });

  it('drops a reply from the topic the student has finished', () => {
    // The exact ST-transition hazard: Topic 1's Review reply landing after the
    // client has already opened Topic 2 at Orientation.
    syncBackendSession(reply({
      session_id: 'SESSION002', concept_id: 'T01', question_id: 'Q-T01-009',
    }));
    expect(useNumeraStore.getState().activeQuestionId).toBeNull();
    expect(useNumeraStore.getState().currentPhase).toBe('ORIENTATION');
  });

  it('still applies a reply that names neither, rather than blacking out', () => {
    // Degrade, do not throw. A backend that stops sending an identifier must
    // not stop the lesson.
    syncBackendSession(reply());
    expect(useNumeraStore.getState().activeQuestionId).toBe('Q-T02-001');
  });
});
