/**
 * Login carries the student's current topic into the next session start.
 *
 * Manjusha (ST008), 21 Sep 2026, mid-way through topic 2: logged out, logged
 * in, and "it took me to phase 4". The backend log shows why — the app started
 * a session with the hard-coded default concept, so the backend opened topic
 * 1's finished review (review_session_opened … ALG-KS3-01 … MASTERED). Nothing
 * in the app carried ALG-ORI-02 across the login.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const login = readFileSync(join(process.cwd(), 'app/login/page.tsx'), 'utf8');

describe('login drops the stored tutoring session', () => {
  it('clears the session id, the ended id and the stale phase', () => {
    expect(login).toMatch(/store\.clearSessionId\(\);\s*\n\s*store\.setEndedSessionId\(null\);\s*\n\s*store\.setCurrentPhase\(''\);/);
  });
});

describe('login seeds the pending topic code', () => {
  it('takes the topic from last_journey_state and hands it to the next start', () => {
    expect(login).toMatch(/last_journey_state\?\.topic_id/);
    expect(login).toMatch(/setPendingTopicCode\(journeyTopic\)/);
  });
  it('routes the topic-scoped screens to that topic, not the local default', () => {
    expect(login).toMatch(/journeyTopic \?\? store\.currentTopicId/);
  });
});
