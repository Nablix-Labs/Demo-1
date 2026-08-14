/**
 * A hint the backend has already authorised must reach the student unasked.
 *
 * Sanya, 12 Aug 2026: on WRONG_1 and WRONG_2 the Student Model returns real
 * hints (`conversation_action: GIVE_HINT`, text in `support_message`). The
 * client only stored them for the "Need help?" replay, so a student who had
 * earned a hint saw nothing unless they knew to press a button.
 */

import { describe, it, expect } from 'vitest';
import { authorisedHint } from '@/lib/interactionPresentation';

type Turn = Parameters<typeof authorisedHint>[0];

const HINT = 'Look at the operation shown in every example. Is it addition or multiplication?';

describe('authorisedHint', () => {
  it('surfaces the hint the backend served on a wrong attempt', () => {
    expect(authorisedHint({
      message: 'Not quite — try once more.',
      support_message: HINT,
      conversation_action: 'GIVE_HINT',
    } as Turn)).toBe(HINT);
  });

  it('stays silent when the turn served no hint', () => {
    expect(authorisedHint({ message: 'Go on.', conversation_action: 'ASK_QUESTION' } as Turn)).toBeNull();
    expect(authorisedHint({ message: 'Go on.', conversation_action: 'GIVE_HINT' } as Turn)).toBeNull();
  });

  it('does not repeat the tutor line back as a hint', () => {
    // When support_message IS the message, showing both says it twice.
    expect(authorisedHint({
      message: HINT, support_message: HINT, conversation_action: 'GIVE_HINT',
    } as Turn)).toBeNull();
  });

  it('ignores whitespace-only support text', () => {
    expect(authorisedHint({
      message: 'Try again.', support_message: '   ', conversation_action: 'GIVE_HINT',
    } as Turn)).toBeNull();
  });

  it('only fires on GIVE_HINT — the backend decides when a hint is earned', () => {
    // A partial answer advances no rung, so nothing may be shown.
    expect(authorisedHint({
      message: 'Keep going.', support_message: HINT, conversation_action: 'ASK_QUESTION',
    } as Turn)).toBeNull();
  });
});
