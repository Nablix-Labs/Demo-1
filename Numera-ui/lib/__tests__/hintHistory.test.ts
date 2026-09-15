/**
 * Issue #312 — a third hint arrived and hints 1 and 2 were gone (Sanya,
 * 14 Sep 2026).
 *
 * The screen held one hint string, so every rung of the support ladder
 * overwrote the one before it.
 */

import { describe, it, expect } from 'vitest';
import { appendHint, hintLabel, MAX_VISIBLE_HINTS } from '@/lib/hintHistory';

describe('support already given stays on the page', () => {
  it('keeps the earlier hints when a new one arrives', () => {
    // The issue itself: by the third press only the third hint was visible,
    // and that is the one written assuming the first two have been read.
    let hints: string[] = [];
    hints = appendHint(hints, 'Look at what changes between the cases.');
    hints = appendHint(hints, 'Compare the second case with the first.');
    hints = appendHint(hints, 'What is added each time?');
    expect(hints).toEqual([
      'Look at what changes between the cases.',
      'Compare the second case with the first.',
      'What is added each time?',
    ]);
  });

  it('keeps them in the order they were served', () => {
    const hints = ['first', 'second'].reduce<string[]>(appendHint, []);
    expect(hints[0]).toBe('first');
  });

  it('does not stack a replay of the rung already showing', () => {
    // Pressing Help when the backend has nothing new to authorise replays the
    // current rung. Twice on screen reads as the tutor stuttering.
    const hints = appendHint(['What is added each time?'], 'What is added each time?');
    expect(hints).toEqual(['What is added each time?']);
  });

  it('ignores surrounding whitespace when spotting that replay', () => {
    expect(appendHint(['a hint'], '  a hint  ')).toEqual(['a hint']);
  });

  it('keeps a returning earlier hint, which is a deliberate move back', () => {
    // Coming back to hint 1 after a cue is the tutor returning to it on
    // purpose. Dropping it would leave the sequence unreadable.
    expect(appendHint(['one', 'two'], 'one')).toEqual(['one', 'two', 'one']);
  });

  it('renders nothing for a rung served with no words', () => {
    expect(appendHint(['one'], '')).toEqual(['one']);
    expect(appendHint(['one'], '   ')).toEqual(['one']);
    expect(appendHint(['one'], null)).toEqual(['one']);
    expect(appendHint(['one'], undefined)).toEqual(['one']);
  });

  it('starts from nothing without throwing', () => {
    expect(appendHint([], 'first hint')).toEqual(['first hint']);
    expect(appendHint([], null)).toEqual([]);
  });

  it('stops the notes covering the canvas the student is working on', () => {
    let hints: string[] = [];
    for (let i = 0; i < 10; i += 1) hints = appendHint(hints, `hint ${i}`);
    expect(hints).toHaveLength(MAX_VISIBLE_HINTS);
    // Oldest dropped, newest kept — the student is being helped now.
    expect(hints[hints.length - 1]).toBe('hint 9');
  });

  it('never mutates the list it was handed', () => {
    const original = ['one'];
    appendHint(original, 'two');
    expect(original).toEqual(['one']);
  });
});

describe('what each note is called', () => {
  it('numbers them once there is more than one to tell apart', () => {
    expect(hintLabel(0, 3)).toBe('Hint 1');
    expect(hintLabel(2, 3)).toBe('Hint 3');
  });

  it('does not number a lone hint, which has nothing to be first of', () => {
    expect(hintLabel(0, 1)).toBe('Gentle hint');
  });
});
