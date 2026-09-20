/**
 * Mastery is recorded under the backend topic id with its title, and the
 * completion screen lists what was actually mastered.
 *
 * ST015, 21 Sep 2026: after mastering ALG-ORI-02 and ALG-ORI-03 in one
 * sitting, Continue on the last review landed on /complete reading
 * "Nothing finished yet" with Algebra / Number / Geometry all "—". The
 * screen counted mastery only against the local three-strand table.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useNumeraStore } from '@/store/useNumeraStore';

const complete = readFileSync(join(process.cwd(), 'app/complete/page.tsx'), 'utf8');
const review = readFileSync(join(process.cwd(), 'app/review/page.tsx'), 'utf8');

beforeEach(() => useNumeraStore.setState({ masteryByTopic: {}, topicTitles: {} }));

describe('setMastery', () => {
  it('keeps the title beside the id', () => {
    useNumeraStore.getState().setMastery('ALG-ORI-03', true, 'Variables and Constants');
    expect(useNumeraStore.getState().masteryByTopic['ALG-ORI-03']).toBe(true);
    expect(useNumeraStore.getState().topicTitles['ALG-ORI-03']).toBe('Variables and Constants');
  });
  it('does not blank a title it was not given', () => {
    useNumeraStore.getState().setMastery('ALG-ORI-03', true, 'Variables and Constants');
    useNumeraStore.getState().setMastery('ALG-ORI-03', true);
    expect(useNumeraStore.getState().topicTitles['ALG-ORI-03']).toBe('Variables and Constants');
  });
});

describe('the completion screen', () => {
  it('lists mastered backend topics by title rather than the local table', () => {
    expect(complete).toMatch(/Object\.keys\(masteryByTopic\)\.filter/);
    expect(complete).toMatch(/topicTitles\[id\] \?\? id/);
  });
  it('is fed by the review page when the outcome is a pass', () => {
    expect(review).toMatch(/if \(outcome === 'pass'\)[\s\S]{0,400}setMastery\(masteredId, true/);
  });
});
