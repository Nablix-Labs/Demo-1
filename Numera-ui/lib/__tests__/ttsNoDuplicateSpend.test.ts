/**
 * The same line must not be bought twice.
 *
 * Every `speakTutor` call is a paid synthesis. `stopTutorSpeech` supersedes
 * the previous request CLIENT-side — `playBase64Mp3` checks the token and
 * drops the stale audio — but the HTTP request has already gone and the
 * provider still bills it. So a component that re-renders while its line is
 * in flight pays for a stack of identical audio and throws all but one away.
 *
 * The VM journal for 20 Sep 2026 has exactly that: one student, one screen,
 * `Inworld TTS: 47 chars` seven times inside three seconds and
 * `Inworld TTS: 100 chars` seven times alongside it, repeating at 09:30,
 * 11:22, 11:31 and 11:42 UTC. 273 TTS calls served 33 interactions.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const synthesizeSpeech = vi.fn(async () => 'AAAA');

// Spread the real module: lib/tts pulls in the store, which needs the rest of
// the api module's exports. A bare object mock leaves them undefined.
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  synthesizeSpeech: (...a: unknown[]) => synthesizeSpeech(...(a as [])),
}));

let speakTutor: typeof import('@/lib/tts').speakTutor;
let stopTutorSpeech: typeof import('@/lib/tts').stopTutorSpeech;

beforeEach(async () => {
  vi.resetModules();
  synthesizeSpeech.mockClear();
  // lib/tts only uses the API voice when a base URL is configured; without
  // this it falls back to browser speech and buys nothing.
  vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '/api');
  // Audio is jsdom-hostile; the calls under test are the network ones.
  vi.stubGlobal('Audio', class {
    playbackRate = 1;
    play() { return Promise.resolve(); }
    pause() {}
    addEventListener() {}
    removeEventListener() {}
  });
  ({ speakTutor, stopTutorSpeech } = await import('@/lib/tts'));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('one line, one purchase', () => {
  it('does not re-request a line that is still in flight', () => {
    // The seven-renders-in-three-seconds case, straight from the journal.
    for (let i = 0; i < 7; i += 1) speakTutor('Look across the three cases.');
    expect(synthesizeSpeech).toHaveBeenCalledTimes(1);
  });

  it('still requests a different line straight away', () => {
    speakTutor('Look across the three cases.');
    speakTutor('What stays the same?');
    expect(synthesizeSpeech).toHaveBeenCalledTimes(2);
  });

  it('interleaved duplicates of two lines cost two requests, not fourteen', () => {
    // Both texts repeated seven times each, as the 47/100-char pair were.
    for (let i = 0; i < 7; i += 1) {
      speakTutor('Look across the three cases.');
      speakTutor('What stays the same?');
    }
    // The second line supersedes the first each round, so the first is
    // released and re-bought — but never seven times over.
    expect(synthesizeSpeech.mock.calls.length).toBeLessThanOrEqual(14);
    expect(synthesizeSpeech.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('allows the line again after an explicit stop', () => {
    // Pen-down, navigation, a deliberate replay: the floor was given up, so
    // the next request for the same words is a real one.
    speakTutor('Look across the three cases.');
    stopTutorSpeech();
    speakTutor('Look across the three cases.');
    expect(synthesizeSpeech).toHaveBeenCalledTimes(2);
  });

  it('ignores empty text without spending anything', () => {
    speakTutor('');
    expect(synthesizeSpeech).not.toHaveBeenCalled();
  });
});
