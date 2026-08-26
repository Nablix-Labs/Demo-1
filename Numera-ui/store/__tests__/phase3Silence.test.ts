/**
 * Tutor ink must not reach the canvas during an independent attempt.
 *
 * Refusing it at the store rather than hiding it at the render is the point:
 * a drawing that is merely hidden is still in the tutor layer, waiting to
 * appear the moment the phase changes — which is precisely when the student
 * moves on to REVIEW and would see corrections for an attempt they had already
 * closed.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

const A_TUTOR_MARK = {
  author: 'tutor' as const,
  mode: 'replace' as const,
  actionId: 'draw-1',
  elements: [{ kind: 'line' as const, points: [0, 0, 10, 10] }],
};

describe('canvas draws during Phase 3', () => {
  beforeEach(() => useNumeraStore.setState({ tutorElements: [], currentPhase: 'GUIDED_PRACTICE' }));

  it('accepts tutor ink in guided practice, where the tutor teaches', () => {
    state().applyCanvasDraw(A_TUTOR_MARK);
    expect(state().tutorElements.length).toBeGreaterThan(0);
  });

  it('refuses tutor ink in independent practice', () => {
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    state().applyCanvasDraw(A_TUTOR_MARK);
    expect(state().tutorElements).toEqual([]);
  });

  it('does not stash the refused ink for the next phase', () => {
    // The failure this guards: a correction arriving during Phase 3, held back,
    // then appearing on the canvas as soon as the phase moved on.
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    state().applyCanvasDraw({ ...A_TUTOR_MARK, actionId: 'draw-2' });
    useNumeraStore.setState({ currentPhase: 'REVIEW' });
    expect(state().tutorElements).toEqual([]);
  });
});

describe('the Phase 3 lock', () => {
  beforeEach(() => useNumeraStore.setState({ phase3LockedQuestionId: null }));

  it('records the question whose attempt was accepted', () => {
    state().lockPhase3Attempt('Q-T03-001');
    expect(state().phase3LockedQuestionId).toBe('Q-T03-001');
  });

  it('is idempotent, so a duplicate reply changes nothing', () => {
    state().lockPhase3Attempt('Q-T03-001');
    state().lockPhase3Attempt('Q-T03-001');
    expect(state().phase3LockedQuestionId).toBe('Q-T03-001');
  });

  it('does not outlive its session', () => {
    // The lock is persisted so a refresh cannot reopen closed evidence — which
    // means it can otherwise survive into the NEXT session and freeze its first
    // question, since a lock held with no active question reads as locked.
    state().lockPhase3Attempt('Q-OLD');
    state().setSessionId('SESSION-NEW');
    expect(state().phase3LockedQuestionId).toBeNull();

    state().lockPhase3Attempt('Q-OLD');
    state().clearSessionId();
    expect(state().phase3LockedQuestionId).toBeNull();
  });

  it('is persisted, so a refresh cannot reopen a closed attempt', () => {
    // Spec §3.3: "Keep the locked state through reconnect." Canvas and
    // transcript are deliberately per-session; this is not, because a student
    // who refreshes would otherwise get their submitted evidence back to edit.
    const persisted = JSON.parse(localStorage.getItem('numera-store') ?? '{}');
    state().lockPhase3Attempt('Q-T03-002');
    const after = JSON.parse(localStorage.getItem('numera-store') ?? '{}');
    expect(Object.keys(after.state ?? persisted.state ?? {})).toContain('phase3LockedQuestionId');
    expect(after.state.phase3LockedQuestionId).toBe('Q-T03-002');
  });
});

describe('the tutor-draw de-duplication window', () => {
  beforeEach(() => useNumeraStore.setState({
    tutorElements: [], currentPhase: 'GUIDED_PRACTICE',
    activeQuestionId: 'Q1', backendSession: null,
  }));

  const mark = (actionId: string) => ({
    author: 'tutor' as const,
    actionId,
    elements: [{ kind: 'text' as const, x: 0.1, y: 0.2, text: 'c + 4' }],
  });

  it('still drops a re-delivered action within one question', () => {
    // The reconnect case the window exists for: the same command arriving
    // twice must not show the tutor annotating twice.
    state().applyCanvasDraw(mark('ACT-1'));
    state().applyCanvasDraw(mark('ACT-1'));
    expect(state().tutorElements).toHaveLength(1);
  });

  it('accepts the same action id again on the next question', () => {
    // The tutor now draws confirmed learner ideas on ordinary turns (Sanya,
    // 18 Aug 2026), so the same idea can be confirmed again on a new question.
    // Before the window was scoped, the second drawing was silently dropped and
    // the canvas stayed blank with nothing reporting why.
    state().applyCanvasDraw(mark('ACT-1'));
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q2',
      questionText: 'Next question', questionType: null,
    });
    state().applyCanvasDraw(mark('ACT-1'));
    expect(state().tutorElements).toHaveLength(1);
    expect(state().tutorElements[0].text).toBe('c + 4');
  });
});
