/**
 * Key Notes pagination — a topic laid out across notebook spreads.
 *
 * The notebook uses fixed-height paper. Real pages do not stretch and they do
 * not scroll, so a topic that carries more than a spread holds has to continue
 * onto the next one, the way a notebook does.
 *
 * This is deliberately a pure function over the content rather than a DOM
 * measurement pass. Measuring would be more precise, but it would also mean the
 * page count changes with font loading and zoom, and it could not be tested
 * without a browser. Costing the sections in abstract units keeps the layout
 * decision testable and stable — the risk worth defending against here is a
 * section silently vanishing between spreads, not a page being 5% under-filled.
 */

import type { KeyNote } from '@/lib/keynotes';

/** Which page of the spread a section belongs on. */
export type Side = 'left' | 'right';

export type SectionKind =
  | 'meaning'
  | 'howToStart'
  | 'steps'
  | 'example'
  | 'formula'
  | 'beCareful'
  | 'tips'
  | 'examTip';

export interface Section {
  kind: SectionKind;
  /** Small-caps label printed above the section, or null for the opener. */
  label: string | null;
  /** A paragraph, or the lines of a list / worked example. */
  body: string | string[];
  /** Layout cost in units — see PAGE_CAPACITY. */
  cost: number;
}

export interface Spread {
  topicId: string;
  left: Section[];
  right: Section[];
  /** 1-based index of this spread within its topic. */
  page: number;
  /** How many spreads this topic occupies in total. */
  pages: number;
}

/**
 * Capacity of a page, in ruled lines.
 *
 * Derived from the page geometry rather than guessed — see Page.tsx, which is
 * the single source of the numbers: a 720px sheet less its padding leaves 652px
 * of writing area, and at a 30px rule that is 21 lines.
 *
 * The left page is worth less because the topic title and the Read control sit
 * above its writing area and eat three lines of it. Getting this wrong is what
 * made the first cut split a topic at half a page.
 */
export const RIGHT_CAPACITY = 21;
export const LEFT_CAPACITY = 18;

/** A section heading occupies exactly one rule. */
const LABEL_COST = 1;

/** Longest line that still fits one rule at the body measure. */
const CHARS_PER_LINE = 55;

const lines = (text: string) => Math.max(1, Math.ceil(text.length / CHARS_PER_LINE));

/** `labelled: false` for the opening description, which prints without a heading. */
const paragraphCost = (text: string, labelled = true) =>
  (labelled ? LABEL_COST : 0) + lines(text);

const listCost = (items: string[]) =>
  LABEL_COST + items.reduce((n, item) => n + lines(item), 0);

/**
 * The sections of a topic, in reading order, split by the page each prefers.
 *
 * Left page carries the narrative — what this is, how to begin, the steps, a
 * worked example. Right page carries the reference material a student scans for
 * during revision — the rule, the traps, the tips, the exam reminder.
 */
export function sectionsFor(note: KeyNote): Record<Side, Section[]> {
  const left: Section[] = [
    {
      kind: 'meaning',
      label: null,
      body: note.meaning,
      cost: paragraphCost(note.meaning, false),
    },
    {
      kind: 'howToStart',
      label: 'How to start',
      body: note.howToStart,
      cost: paragraphCost(note.howToStart),
    },
    { kind: 'steps', label: 'Steps to follow', body: note.steps, cost: listCost(note.steps) },
    { kind: 'example', label: 'Mini example', body: note.example, cost: listCost(note.example) },
  ];

  const right: Section[] = [
    { kind: 'formula', label: 'Formula / rule', body: note.formula, cost: paragraphCost(note.formula) },
    {
      kind: 'beCareful',
      label: 'Be careful with',
      body: note.beCareful,
      cost: listCost(note.beCareful),
    },
    { kind: 'tips', label: 'Tips & tricks', body: note.tips, cost: listCost(note.tips) },
    { kind: 'examTip', label: 'Exam reminder', body: note.examTip, cost: paragraphCost(note.examTip) },
  ];

  return { left, right };
}

/** Greedily fill pages to `capacity`, never splitting a section. */
function paginate(sections: Section[], capacity: number): Section[][] {
  const pages: Section[][] = [];
  let current: Section[] = [];
  let used = 0;

  for (const section of sections) {
    // A section larger than a whole page still gets its own page rather than
    // being dropped — better an overfull page than missing revision content.
    if (current.length > 0 && used + section.cost > capacity) {
      pages.push(current);
      current = [];
      used = 0;
    }
    current.push(section);
    used += section.cost;
  }

  if (current.length > 0) pages.push(current);
  return pages;
}

/**
 * Lay a topic out across however many spreads it needs.
 *
 * Both sides are paginated independently and then zipped, so a long left page
 * does not push the right page's content out of alignment with it. The spread
 * count is whichever side needs more; the shorter side simply runs out of
 * content and its later pages are empty, exactly as a notebook would look.
 */
export function spreadsFor(note: KeyNote): Spread[] {
  const { left, right } = sectionsFor(note);
  const leftPages = paginate(left, LEFT_CAPACITY);
  const rightPages = paginate(right, RIGHT_CAPACITY);
  const pages = Math.max(leftPages.length, rightPages.length);

  return Array.from({ length: pages }, (_, i) => ({
    topicId: note.id,
    left: leftPages[i] ?? [],
    right: rightPages[i] ?? [],
    page: i + 1,
    pages,
  }));
}

/** Every spread of every topic, in order — what the notebook flips through. */
export function spreadsForAll(notes: KeyNote[]): Spread[] {
  return notes.flatMap(spreadsFor);
}
