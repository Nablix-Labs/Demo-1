/**
 * Talking over the tutor.
 *
 * The two facts needed to detect it live on opposite sides: only the server
 * knows the student started speaking, only the client knows audio is still
 * playing. Aditya tried it server-side alone on 17 Aug 2026 and it fired on
 * every turn — a normal reply is also a StartOfTurn, and nothing told the server
 * playback had ended, so it could not tell an answer from an interruption.
 *
 * These tests are mostly about NOT firing. Cutting the tutor off mid-sentence
 * for a student who did not speak is the same failure aimed the other way, and
 * it is the one a rule like this fails into.
 */

import { describe, expect, it } from 'vitest';
import { interruptsTutor } from '@/lib/bargeIn';

describe('a partial transcript', () => {
  it('interrupts the tutor when audio is still playing', () => {
    expect(interruptsTutor({ audioPlaying: true, text: 'wait no' })).toBe(true);
  });

  it('is an ordinary answer once the tutor has finished', () => {
    // The normal case, and the one the server-side attempt could not separate:
    // the student speaking after the tutor stopped is not an interruption.
    expect(interruptsTutor({ audioPlaying: false, text: 'n plus five' })).toBe(false);
  });
});

describe('what must not stop the tutor', () => {
  it('an empty partial', () => {
    // Deepgram emits these around the edges of speech. Stopping the tutor
    // because the recogniser twitched cuts off a student who never spoke.
    expect(interruptsTutor({ audioPlaying: true, text: '' })).toBe(false);
    expect(interruptsTutor({ audioPlaying: true, text: '   ' })).toBe(false);
  });

  it('a partial with no text field at all', () => {
    expect(interruptsTutor({ audioPlaying: true, text: null })).toBe(false);
    expect(interruptsTutor({ audioPlaying: true, text: undefined })).toBe(false);
  });

  it('speech when nothing is playing, however loud', () => {
    expect(interruptsTutor({ audioPlaying: false, text: 'HELLO HELLO' })).toBe(false);
  });
});
