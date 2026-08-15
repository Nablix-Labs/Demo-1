/**
 * The streaming audio player must NEVER strand a turn.
 *
 * Every no-audio failure — a browser without MediaSource MP3 (iPhone Safari
 * < 17.1), a refused play(), a stream that never arrives — used to leave
 * `voiceStatus` pinned at 'speaking' with the mic shut: the lesson was dead
 * after one turn. The invariant under test: whatever happens to the audio,
 * onIdle is eventually reported, because that is what hands the floor back to
 * the student.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tutorAudioStream, stopTutorSpeech } from '@/lib/tts';

beforeEach(() => {
  vi.useFakeTimers();
  // jsdom has no MediaSource at all — exactly the unsupported-browser case.
  // (If a future jsdom adds one, delete it so the test still exercises the path.)
  delete (window as { MediaSource?: unknown }).MediaSource;
});
afterEach(() => {
  vi.useRealTimers();
  tutorAudioStream.setOnIdle(null);
});

describe('TutorAudioStream on a browser without MediaSource', () => {
  it('still reports idle — the mic gate cannot be left shut', async () => {
    const idle = vi.fn();
    tutorAudioStream.setOnIdle(idle);

    tutorAudioStream.begin('two plus two is four');
    // The fallback chain runs (no API base in tests → speakBrowser → no
    // speechSynthesis in jsdom → immediate onEnd). Flush the microtasks.
    await vi.runAllTimersAsync();

    expect(idle).toHaveBeenCalled();
  });

  it('reports idle even with no fallback text at all', async () => {
    const idle = vi.fn();
    tutorAudioStream.setOnIdle(idle);

    tutorAudioStream.begin(undefined);
    await vi.runAllTimersAsync();

    expect(idle).toHaveBeenCalled();
  });
});

describe('stopTutorSpeech silences the streaming player too', () => {
  it('does not report idle from hardStop — the caller owns what happens next', async () => {
    const idle = vi.fn();
    tutorAudioStream.setOnIdle(idle);

    stopTutorSpeech();
    await vi.runAllTimersAsync();

    expect(idle).not.toHaveBeenCalled();
  });
});
