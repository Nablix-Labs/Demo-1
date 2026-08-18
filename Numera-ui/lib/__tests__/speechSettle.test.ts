import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SpeechSettleTimer, UTTERANCE_END_MS } from '@/lib/speechSettle';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('a turn has settled only when the student has actually stopped', () => {
  it('settles once no further speech arrives for the utterance window', () => {
    const settled = vi.fn();
    new SpeechSettleTimer(settled).noteSpeech();
    vi.advanceTimersByTime(UTTERANCE_END_MS - 1);
    expect(settled).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(settled).toHaveBeenCalledTimes(1);
  });

  /**
   * The whole point. transcript_final fires per Deepgram segment, so "It is,
   * … 5" delivers a final for "It is" while the student is still answering.
   * Treating that as the end of the turn is what splits one answer in two.
   */
  it('resumed speech cancels a pending settle', () => {
    const settled = vi.fn();
    const t = new SpeechSettleTimer(settled);
    t.noteSpeech();                      // "It is"
    vi.advanceTimersByTime(1_400);       // nearly settled…
    t.noteSpeech();                      // "…5" — still talking
    vi.advanceTimersByTime(1_400);
    expect(settled).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(settled).toHaveBeenCalledTimes(1);
  });

  it('settles exactly once for one spoken turn', () => {
    const settled = vi.fn();
    const t = new SpeechSettleTimer(settled);
    t.noteSpeech();
    t.noteSpeech();
    t.noteSpeech();
    vi.advanceTimersByTime(UTTERANCE_END_MS * 3);
    expect(settled).toHaveBeenCalledTimes(1);
  });

  it('a resolved or failed turn cancels it outright', () => {
    const settled = vi.fn();
    const t = new SpeechSettleTimer(settled);
    t.noteSpeech();
    t.cancel();
    vi.advanceTimersByTime(UTTERANCE_END_MS * 2);
    expect(settled).not.toHaveBeenCalled();
    expect(t.pending).toBe(false);
  });

  it('matches the window the voice server actually uses', () => {
    // If Deepgram's utterance_end_ms changes server-side, this must move with
    // it — the same number the turn watchdog's budget is derived from.
    expect(UTTERANCE_END_MS).toBe(1_500);
  });
});
