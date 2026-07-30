/**
 * The rescue must fire when a turn is genuinely stuck, and must NOT fire
 * otherwise.
 *
 * The second half matters more than the first. A `stop` sent while the server
 * is still producing a reply can cancel it mid-flight (streaming_server.py:503
 * cancels the Deepgram receiver task after 10s, and that task is what runs the
 * tutor turn). So a watchdog that is merely eager would break responses that
 * work today — a worse outcome than the bug it fixes.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TurnWatchdog, TURN_RESCUE_MS } from '@/lib/turnWatchdog';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('TurnWatchdog: rescues a turn the server never finished', () => {
  it('forces finalisation when no reply ever arrives', () => {
    const onStuck = vi.fn();
    new TurnWatchdog(onStuck).noteStudentSpeech();

    vi.advanceTimersByTime(TURN_RESCUE_MS);
    expect(onStuck).toHaveBeenCalledTimes(1);
  });

  it('stays quiet until the window has fully elapsed', () => {
    const onStuck = vi.fn();
    new TurnWatchdog(onStuck).noteStudentSpeech();

    vi.advanceTimersByTime(TURN_RESCUE_MS - 1);
    expect(onStuck).not.toHaveBeenCalled();
  });

  it('does nothing at all until the student has actually spoken', () => {
    const onStuck = vi.fn();
    const w = new TurnWatchdog(onStuck);

    expect(w.armed).toBe(false);
    vi.advanceTimersByTime(TURN_RESCUE_MS * 3);
    expect(onStuck).not.toHaveBeenCalled();
  });

  it('rescues only once, not on a repeating timer', () => {
    const onStuck = vi.fn();
    const w = new TurnWatchdog(onStuck);
    w.noteStudentSpeech();

    vi.advanceTimersByTime(TURN_RESCUE_MS * 4);
    expect(onStuck).toHaveBeenCalledTimes(1);
    expect(w.armed).toBe(false);
  });
});

describe('TurnWatchdog: never cancels a reply that is still coming', () => {
  it('stands down as soon as the tutor responds', () => {
    const onStuck = vi.fn();
    const w = new TurnWatchdog(onStuck);

    w.noteStudentSpeech();
    vi.advanceTimersByTime(TURN_RESCUE_MS - 1);
    w.noteTurnResolved();
    vi.advanceTimersByTime(TURN_RESCUE_MS * 2);

    expect(onStuck).not.toHaveBeenCalled();
  });

  it('outlasts the slowest reply the server can produce', () => {
    // UtteranceEnd's 1.5s silence threshold plus the tutor call's own 15s
    // timeout. By then the server has sent either tutor_response or error, and
    // both disarm us. If this ever fails, the window is too short and the
    // rescue can cancel a working response.
    const SLOWEST_SERVER_REPLY_MS = 1_500 + 15_000;
    expect(TURN_RESCUE_MS).toBeGreaterThan(SLOWEST_SERVER_REPLY_MS);
  });

  it('restarts the clock while the student is still talking', () => {
    const onStuck = vi.fn();
    const w = new TurnWatchdog(onStuck);

    // Three segments of a long answer, each nearly a full window apart.
    w.noteStudentSpeech();
    vi.advanceTimersByTime(TURN_RESCUE_MS - 1);
    w.noteStudentSpeech();
    vi.advanceTimersByTime(TURN_RESCUE_MS - 1);
    w.noteStudentSpeech();
    vi.advanceTimersByTime(TURN_RESCUE_MS - 1);

    // Well past 20s of wall clock, but never 20s since they last spoke.
    expect(onStuck).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(onStuck).toHaveBeenCalledTimes(1);
  });
});

describe('TurnWatchdog: does not outlive its socket', () => {
  it('cannot fire after dispose', () => {
    const onStuck = vi.fn();
    const w = new TurnWatchdog(onStuck);

    w.noteStudentSpeech();
    w.dispose();
    vi.advanceTimersByTime(TURN_RESCUE_MS * 2);

    expect(onStuck).not.toHaveBeenCalled();
    expect(w.armed).toBe(false);
  });

  it('is safe to dispose repeatedly and before ever arming', () => {
    const w = new TurnWatchdog(vi.fn());
    expect(() => {
      w.dispose();
      w.dispose();
    }).not.toThrow();
  });
});
