/**
 * A stored session that cannot be re-read is SAID, not rendered blank.
 *
 * ST015, 21 Sep 2026: GET /session took 55s and 503'd (the backend failing to
 * build a Phase 4 review on every read). The client timed out at 30s, logged
 * "session resume failed (will stay on the stored session)" and then drew the
 * lesson: empty question, live mic, "Listening…". Nothing told the student
 * anything had gone wrong, and nothing offered a way out.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useNumeraStore } from '@/store/useNumeraStore';

const page = readFileSync(join(process.cwd(), 'app/page.tsx'), 'utf8');
const hook = readFileSync(join(process.cwd(), 'hooks/useDemoTutor.ts'), 'utf8');

beforeEach(() => useNumeraStore.setState({ sessionResumeFailed: false }));

describe('sessionResumeFailed', () => {
  it('is a plain flag the hook can raise and clear', () => {
    useNumeraStore.getState().setSessionResumeFailed(true);
    expect(useNumeraStore.getState().sessionResumeFailed).toBe(true);
    useNumeraStore.getState().setSessionResumeFailed(false);
    expect(useNumeraStore.getState().sessionResumeFailed).toBe(false);
  });

  it('is raised where the resume gives up, and cleared when a record arrives', () => {
    const giveUp = hook.indexOf('session resume failed (will stay on the stored session)');
    expect(giveUp).toBeGreaterThan(-1);
    expect(hook.slice(giveUp, giveUp + 400)).toMatch(/setSessionResumeFailed\(true\)/);
    expect(hook).toMatch(/s\.setSessionResumeFailed\(false\);\s*\n\s*s\.setBackendSession\(rec\)/);
  });

  it('takes the lesson page to the unavailable screen with a retry that re-reads', () => {
    expect(page).toMatch(/if \(startError \|\| resumeFailed\)/);
    expect(page).toMatch(/Couldn't reload your lesson/);
    expect(page).toMatch(/setSessionResumeFailed\(false\);\s*\n\s*void resumeSession\(\)/);
  });
});
