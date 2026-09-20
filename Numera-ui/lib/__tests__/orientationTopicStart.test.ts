/**
 * Orientation opens the session for the topic in the URL.
 *
 * ST015, 21 Sep 2026: /orientation/?topic=ALG-ORI-03 on a fresh load sent
 * POST /session/start with concept_id ALG_LINEAR_ONE_STEP — the store's
 * unpersisted default — and the backend opened topic 1's finished review
 * (42s, past the client timeout). The diagnostic got this fix in #353; the
 * orientation route never did.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const src = readFileSync(join(process.cwd(), 'app/orientation/OrientationClient.tsx'), 'utf8');

describe('orientation session start', () => {
  it('passes the route topic as the topic code', () => {
    expect(src).toMatch(/beginSession\(activeConceptId, 'TEXT', topicId\)/);
  });
});
