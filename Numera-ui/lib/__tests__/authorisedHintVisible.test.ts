/**
 * An authorised hint has to reach the SCREEN, not just the transcript.
 *
 * Sanya, 13 Aug 2026: "hints are gone noww". They were not gone — the backend
 * served them, `applyInteractionSupport` stored them and `hint_count` counted
 * them. They were appended to the transcript as an ordinary tutor bubble, so
 * they looked exactly like the tutor talking, and disappeared completely when
 * the transcript panel was collapsed — a persisted preference, so one collapse
 * hid every hint from then on.
 *
 * Which is why these assert on `visibleHint` (the store field the card renders
 * from) rather than on the transcript: a hint that is only in the transcript is
 * the bug, and a test that accepted it would pass on the broken version.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

const turn = (over: Record<string, unknown> = {}) => ({
  message: 'Have another look at the middle step.',
  support_message: 'What happens to the +5 each time?',
  conversation_action: 'GIVE_HINT',
  show_visual_cue: false,
  ...over,
}) as Parameters<typeof applyInteractionSupport>[0];

beforeEach(() => {
  useNumeraStore.setState({
    visibleHint: null,
    lastHintText: null,
    currentPhase: 'GUIDED_PRACTICE',
    activeQuestionId: 'Q-T01-004',
  });
});

describe('an authorised hint', () => {
  it('goes on screen, not only into the record', () => {
    // Sanya's repro: two wrong answers, and the Student Model returns a hint
    // with conversation_action GIVE_HINT.
    applyInteractionSupport(turn());
    expect(state().visibleHint).toBe('What happens to the +5 each time?');
  });

  it('is still kept for the Need help? replay', () => {
    // The two fields are not the same thing: this one has to survive dismissal.
    applyInteractionSupport(turn());
    expect(state().lastHintText).toBe('What happens to the +5 each time?');
  });

  it('is not shown when the turn served no hint', () => {
    applyInteractionSupport(turn({ conversation_action: 'ASK_QUESTION' }));
    expect(state().visibleHint).toBeNull();
  });

  it('is not shown twice when it only repeats the tutor line', () => {
    // Same sentence in both fields — the student is already reading it as the
    // tutor's reply, so a card would put it on screen a second time.
    applyInteractionSupport(turn({ support_message: 'Have another look at the middle step.' }));
    expect(state().visibleHint).toBeNull();
  });

  it('survives an ordinary reply that carries no support', () => {
    // The hint stays up while the student works on it. Only a new question
    // takes it down — the tutor does not withdraw a hint by saying something
    // else.
    applyInteractionSupport(turn());
    applyInteractionSupport(turn({ conversation_action: 'ASK_QUESTION', support_message: null }));
    expect(state().visibleHint).toBe('What happens to the +5 each time?');
  });

  it('is replaced when a later turn serves a different one', () => {
    applyInteractionSupport(turn());
    applyInteractionSupport(turn({ support_message: 'Try the smallest value first.' }));
    expect(state().visibleHint).toBe('Try the smallest value first.');
  });
});

describe('scope', () => {
  it('comes down when the question changes', () => {
    applyInteractionSupport(turn());
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-005', questionText: 'Next one',
    });
    expect(state().visibleHint).toBeNull();
  });

  it('stays up while the student is on the same question', () => {
    applyInteractionSupport(turn());
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-004', questionText: null,
    });
    expect(state().visibleHint).toBe('What happens to the +5 each time?');
  });
});
