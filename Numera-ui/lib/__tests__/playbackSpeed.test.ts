/**
 * The orientation video's speed control (Manjusha, 30 Aug 2026).
 *
 * The behaviour worth pinning is not "a number is stored" — it is that the
 * choice survives the player being REMOUNTED, because the orientation screen
 * replays a video by bumping a React key and moves between several videos in
 * one bundle. A rate that reset on either would look like a broken control.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import {
  PLAYBACK_RATES, DEFAULT_RATE, currentRate, rememberRate, resetRate, rateLabel,
} from '@/lib/playbackSpeed';

beforeEach(() => resetRate());

describe('the offered rates', () => {
  it('opens at normal speed', () => {
    expect(currentRate()).toBe(1);
    expect(DEFAULT_RATE).toBe(1);
  });

  it('offers both slower and faster than normal', () => {
    // A student who cannot follow the explanation needs slower as much as a
    // student re-watching needs faster.
    expect(PLAYBACK_RATES.some((r) => r < 1)).toBe(true);
    expect(PLAYBACK_RATES.some((r) => r > 1)).toBe(true);
  });

  it('stops at 2x', () => {
    expect(Math.max(...PLAYBACK_RATES)).toBe(2);
  });
});

describe('remembering the choice', () => {
  it('holds it for the next player', () => {
    // "Watch again" remounts the player; the next read is that new player's
    // opening rate.
    rememberRate(1.5);
    expect(currentRate()).toBe(1.5);
  });

  it('returns the rate it settled on', () => {
    expect(rememberRate(0.75)).toBe(0.75);
  });

  it('falls back to normal speed for a rate it does not offer', () => {
    // playbackRate accepts any positive number, so an unoffered value would be
    // applied by the browser and then be unshowable and un-undoable in a
    // control that only knows five buttons.
    rememberRate(1.5);
    expect(rememberRate(3)).toBe(1);
    expect(currentRate()).toBe(1);
  });

  it('ignores nonsense rather than pausing or reversing the video', () => {
    expect(rememberRate(0)).toBe(1);
    expect(rememberRate(-2)).toBe(1);
    expect(rememberRate(Number.NaN)).toBe(1);
  });
});

describe('the label', () => {
  it('reads as a speed, not a measurement', () => {
    expect(rateLabel(1)).toBe('1×');
    expect(rateLabel(1.5)).toBe('1.5×');
    expect(rateLabel(0.75)).toBe('0.75×');
  });
});
