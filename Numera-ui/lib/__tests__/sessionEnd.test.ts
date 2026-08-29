/**
 * What /session/end must carry for the Review screen to open.
 *
 * The regression these guard is a live one: `session_review` was deleted from
 * the backend on 18 Aug 2026 (Sanya PR #155, Phase 4 replaces it), the client
 * still required it, and every student finishing a topic was shown "your
 * session review could not be loaded" instead of their results.
 */

import { describe, expect, it } from 'vitest';
import { sessionEndSummary, storeEndedSession } from '@/lib/sessionEnd';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionEndResponse } from '@/lib/api';

const ended = (over: Partial<SessionEndResponse> = {}) => ({
  session_id: 'SESSION1',
  concept_id: 'ALG-KS3-01',
  status: 'ended',
  current_question: 'Find a rule.',
  hint_count: 1,
  attempt_count: 2,
  ...over,
}) as SessionEndResponse;

describe('ending a session', () => {
  it('opens the review with no session_review at all', () => {
    // The field no longer exists on the backend. Requiring it turned a
    // perfectly good session into an error page for every student.
    const summary = sessionEndSummary(ended());
    expect(summary.session_id).toBe('SESSION1');
    expect(summary.attempts).toBe(2);
  });

  it('opens the review with no phase 4 review either', () => {
    // A topic can end before Phase 4 generates anything. That is a screen with
    // less on it, not a screen that failed.
    expect(() => sessionEndSummary(ended({ phase4_review: null } as Partial<SessionEndResponse>)))
      .not.toThrow();
  });

  it('fails when no session came back', () => {
    // The one real failure: nothing was ended, so there is nothing to review
    // and the backend has left the session open.
    expect(() => sessionEndSummary(null)).toThrow(/no summary/i);
    expect(() => sessionEndSummary({} as SessionEndResponse)).toThrow(/no summary/i);
  });
});

describe('the completed record survives into Review', () => {
  it('keeps phase4_review after the live session is cleared', () => {
    // The bug this guards: `clearSessionId` also nulls `backendSession`, so the
    // review the backend had just generated was destroyed between arriving and
    // being rendered. It painted on one frame and vanished on the next.
    const phase4_review = { student_insights: { strength_summary: 'Good start.' } };
    const res = ended({ phase4_review } as Partial<SessionEndResponse>);

    useNumeraStore.getState().setSessionId('SESSION1');
    storeEndedSession(res, sessionEndSummary(res));

    const state = useNumeraStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.backendSession).not.toBeNull();
    expect(state.backendSession).toMatchObject({ phase4_review });
  });

  it('still carries forward what only the in-session record held', () => {
    // Merged, not replaced: /session/end does not resend the question set.
    useNumeraStore.getState().setSessionId('SESSION1');
    useNumeraStore.getState().setBackendSession(
      { session_id: 'SESSION1', current_question: 'Find a rule.' } as never,
    );

    const res = ended({ current_question: null } as Partial<SessionEndResponse>);
    storeEndedSession(res, sessionEndSummary(res));

    expect(useNumeraStore.getState().backendSession).toMatchObject({ status: 'ended' });
  });
});

describe('where an ended session leaves the student', () => {
  it('moves the client phase to REVIEW', () => {
    // /session/end returns the record with current_phase UNCHANGED
    // (session_service.py:1556 updates status, message and session_summary and
    // nothing else). usePhaseRouting re-asserts the store's phase on every
    // screen, so leaving it at INDEPENDENT_PRACTICE pulled the student off
    // /review and back to /practice, where the question they had just finished
    // was still sitting. Manjusha, 29 Aug: "Why it's is taking me to this
    // question".
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    useNumeraStore.getState().setSessionId('SESSION1');

    const res = ended({ current_phase: 'INDEPENDENT_PRACTICE' } as Partial<SessionEndResponse>);
    storeEndedSession(res, sessionEndSummary(res));

    expect(useNumeraStore.getState().currentPhase).toBe('REVIEW');
  });

  it('does so even though the record it merged still says otherwise', () => {
    // The merged record keeps the backend's own field verbatim — the phase the
    // CLIENT routes on is what changes. Asserting both keeps the two from
    // being quietly collapsed into one.
    useNumeraStore.getState().setSessionId('SESSION1');
    const res = ended({ current_phase: 'INDEPENDENT_PRACTICE' } as Partial<SessionEndResponse>);
    storeEndedSession(res, sessionEndSummary(res));

    expect(useNumeraStore.getState().backendSession).toMatchObject({
      current_phase: 'INDEPENDENT_PRACTICE',
    });
    expect(useNumeraStore.getState().currentPhase).toBe('REVIEW');
  });
});
