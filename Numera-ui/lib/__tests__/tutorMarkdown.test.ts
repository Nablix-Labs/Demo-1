/**
 * The tutor's emphasis must reach the ear as words, not as markup.
 *
 * Observed live 26 Aug 2026: the tutor replied "explain why **n + 4** works"
 * and the markers went both to the screen and to the TTS engine. The render
 * half is covered by TutorProse (no DOM test runner in this project — verified
 * in the browser); this covers the string half, which is what speech is given.
 */
import { describe, it, expect } from 'vitest';
import { stripTutorMarkdown } from '../tutorMarkdown';

describe('stripTutorMarkdown', () => {
  it('removes the markers and keeps the words', () => {
    expect(stripTutorMarkdown('explain why **n + 4** works')).toBe('explain why n + 4 works');
  });

  it('handles several runs in one reply', () => {
    expect(stripTutorMarkdown('**a** then **b**')).toBe('a then b');
  });

  it('leaves plain text alone', () => {
    expect(stripTutorMarkdown('what is the operation?')).toBe('what is the operation?');
  });

  it('leaves a lone asterisk alone — 3 * 4 is multiplication, not markup', () => {
    expect(stripTutorMarkdown('3 * 4 = 12')).toBe('3 * 4 = 12');
  });

  it('leaves an unclosed marker alone rather than guessing', () => {
    expect(stripTutorMarkdown('careful with **n')).toBe('careful with **n');
  });
});
