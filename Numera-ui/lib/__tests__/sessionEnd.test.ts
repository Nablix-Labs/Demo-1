/**
 * What /session/end must carry for the Review screen to open.
 *
 * The regression these guard is a live one: `session_review` was deleted from
 * the backend on 18 Aug 2026 (Sanya PR #155, Phase 4 replaces it), the client
 * still required it, and every student finishing a topic was shown "your
 * session review could not be loaded" instead of their results.
 */

import { describe, expect, it } from 'vitest';
import { sessionEndSummary } from '@/lib/sessionEnd';
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
