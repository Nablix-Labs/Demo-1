/**
 * The risk this file defends against is content loss.
 *
 * A student revising before an exam cannot tell that "Be careful with" was
 * dropped between spread 1 and spread 2 — the page looks complete either way.
 * So the load-bearing test is the round trip: every section of every topic
 * appears exactly once across that topic's spreads.
 */

import { describe, it, expect } from 'vitest';
import { KEY_NOTES, type KeyNote } from '@/lib/keynotes';
import {
  spreadsFor,
  spreadsForAll,
  sectionsFor,
  LEFT_CAPACITY,
  RIGHT_CAPACITY,
  type Section,
} from '@/lib/keynotes-paginate';

const kinds = (sections: Section[]) => sections.map((s) => s.kind);

const short: KeyNote = {
  id: 'short',
  topic: 'Short topic',
  meaning: 'Brief.',
  howToStart: 'Start.',
  steps: ['One.'],
  beCareful: ['Careful.'],
  tips: ['Tip.'],
  formula: 'a = b',
  example: ['1 + 1 = 2'],
  examTip: 'Check it.',
};

const long: KeyNote = {
  ...short,
  id: 'long',
  topic: 'Long topic',
  steps: Array.from({ length: 20 }, (_, i) => `Step ${i + 1} with a good deal of explanatory text.`),
  beCareful: Array.from({ length: 15 }, (_, i) => `Careful about the ${i + 1}th subtle trap here.`),
};

describe('spreadsFor', () => {
  it('puts a short topic on a single spread', () => {
    const spreads = spreadsFor(short);
    expect(spreads).toHaveLength(1);
    expect(spreads[0].page).toBe(1);
    expect(spreads[0].pages).toBe(1);
  });

  it('splits a long topic across several spreads', () => {
    const spreads = spreadsFor(long);
    expect(spreads.length).toBeGreaterThan(1);
    expect(spreads.every((s) => s.pages === spreads.length)).toBe(true);
    expect(spreads.map((s) => s.page)).toEqual(
      Array.from({ length: spreads.length }, (_, i) => i + 1),
    );
  });

  it('keeps every section exactly once when it splits', () => {
    const { left, right } = sectionsFor(long);
    const spreads = spreadsFor(long);

    expect(spreads.flatMap((s) => kinds(s.left))).toEqual(kinds(left));
    expect(spreads.flatMap((s) => kinds(s.right))).toEqual(kinds(right));
  });

  it('loses nothing for any real topic', () => {
    for (const note of KEY_NOTES) {
      const { left, right } = sectionsFor(note);
      const spreads = spreadsFor(note);
      expect(spreads.flatMap((s) => kinds(s.left))).toEqual(kinds(left));
      expect(spreads.flatMap((s) => kinds(s.right))).toEqual(kinds(right));
    }
  });

  it('never splits a section across two pages', () => {
    const seen = new Set<string>();
    for (const spread of spreadsFor(long)) {
      for (const section of [...spread.left, ...spread.right]) {
        expect(seen.has(section.kind)).toBe(false);
        seen.add(section.kind);
      }
    }
  });

  it('fills a page before starting the next', () => {
    // Every page except the last of its side must be full enough that the first
    // section of the following page genuinely would not have fitted.
    const spreads = spreadsFor(long);
    const capacity = { left: LEFT_CAPACITY, right: RIGHT_CAPACITY };
    for (const side of ['left', 'right'] as const) {
      const pages = spreads.map((s) => s[side]).filter((p) => p.length > 0);
      pages.forEach((page, i) => {
        const next = pages[i + 1];
        if (!next || next.length === 0) return;
        const used = page.reduce((n, s) => n + s.cost, 0);
        expect(used + next[0].cost).toBeGreaterThan(capacity[side]);
      });
    }
  });

  it('gives an oversized section its own page rather than dropping it', () => {
    const huge: KeyNote = {
      ...short,
      id: 'huge',
      howToStart: 'x'.repeat(LEFT_CAPACITY * 200),
    };
    const spreads = spreadsFor(huge);
    const left = spreads.flatMap((s) => kinds(s.left));
    expect(left).toContain('howToStart');
    expect(left.filter((k) => k === 'howToStart')).toHaveLength(1);
  });
});

describe('spreadsForAll', () => {
  it('covers every topic and keeps them in order', () => {
    const spreads = spreadsForAll(KEY_NOTES);
    const order = [...new Set(spreads.map((s) => s.topicId))];
    expect(order).toEqual(KEY_NOTES.map((n) => n.id));
  });

  it('returns nothing for no topics', () => {
    expect(spreadsForAll([])).toEqual([]);
  });
});
