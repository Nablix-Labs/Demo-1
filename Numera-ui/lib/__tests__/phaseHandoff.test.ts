/**
 * The handoff between one phase's screen and the next.
 *
 * Both bugs these cover were found by a tester rather than by a test, because
 * the screens unpacked the session record by hand and each unpacked it
 * differently. The rule now lives in one function, so it can be checked here.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { applyPhaseHandoff } from '@/lib/phaseHandoff';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionRecord } from '@/lib/api';

const state = () => useNumeraStore.getState();

/** A completion response entering Phase 2, with only the fields in play here. */
function enteringGuidedPractice(over: Partial<SessionRecord> = {}): SessionRecord {
  return {
    current_phase: 'GUIDED_PRACTICE',
    question_id: 'Q-T01-001',
    current_question: '3 + 5, 9 + 5, 14 + 5 — what is the general rule?',
    message: "Nice work. Here's the next question — take your time.",
    ...over,
  } as SessionRecord;
}

describe('applyPhaseHandoff', () => {
  beforeEach(() =>
    // The state the diagnostic leaves behind: its question, its choices, its pick.
    useNumeraStore.setState({
      currentPhase: 'DIAGNOSTIC',
      questionText: 'Which is the general rule?',
      activeQuestionId: 'Q-D1',
      questionType: 'SINGLE_CHOICE',
      questionOptions: [
        { option_id: 'A', text: '12 + 4' },
        { option_id: 'B', text: 'n + 4' },
      ],
      selectedOptionId: 'B',
      transcript: [],
      pendingTutorSpeech: null,
      backendSession: null,
    }),
  );

  it('does not leave the previous phase’s options under the new question', () => {
    // Manjusha, 8 Aug: canvas asked "3 + 5, 9 + 5, 14 + 5" while the choices
    // below it still read "2 + 4, 7 + 4, 12 + 4".
    applyPhaseHandoff(enteringGuidedPractice());

    expect(state().questionOptions).toEqual([]);
    expect(state().selectedOptionId).toBeNull();
    expect(state().questionText).toBe('3 + 5, 9 + 5, 14 + 5 — what is the general rule?');
    expect(state().currentPhase).toBe('GUIDED_PRACTICE');
  });

  it('keeps the line that introduces the new phase', () => {
    // The lesson page speaks an opening line only when IT starts the session.
    // Arriving with one already open, this is the student's only greeting.
    applyPhaseHandoff(enteringGuidedPractice());

    const spoken = state().transcript.filter((m) => m.role === 'ai').map((m) => m.text);
    expect(spoken).toEqual(["Nice work. Here's the next question — take your time."]);
  });

  it('queues the line for the arriving screen to speak', () => {
    // Row 4: the line was shown and never voiced, on a voice-first product.
    // It cannot be spoken here — this screen is unmounting — so it is queued.
    applyPhaseHandoff(enteringGuidedPractice());
    expect(state().pendingTutorSpeech).toBe("Nice work. Here's the next question — take your time.");
  });

  it('hands the queued line over exactly once', () => {
    // React mounts effects twice in development; a read-then-clear pair would
    // let both mounts speak before the clear landed.
    applyPhaseHandoff(enteringGuidedPractice());
    expect(state().claimPendingTutorSpeech()).toBe("Nice work. Here's the next question — take your time.");
    expect(state().claimPendingTutorSpeech()).toBeNull();
  });

  it('queues nothing to speak when there is nothing to say', () => {
    applyPhaseHandoff(enteringGuidedPractice({ message: '   ' }));
    expect(state().pendingTutorSpeech).toBeNull();
  });

  it('adds no empty bubble when the record carries no message', () => {
    applyPhaseHandoff(enteringGuidedPractice({ message: '   ' }));
    expect(state().transcript).toHaveLength(0);
  });

  it('routes to a phase that has no question of its own without stranding the old one', () => {
    // Orientation has no question; carrying the diagnostic's forward is the
    // 28 Jul bug, and carrying its options forward is the 8 Aug one.
    applyPhaseHandoff(
      enteringGuidedPractice({
        current_phase: 'CONCEPT_ORIENTATION',
        question_id: null,
        current_question: null,
      }),
    );

    expect(state().questionText).toBe('');
    expect(state().activeQuestionId).toBeNull();
    expect(state().questionOptions).toEqual([]);
  });
});
