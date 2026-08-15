/**
 * Phase 1 worked-example walkthrough controls.
 *
 * "Resume and start again not working" (Manjusha, row 44, 11 Aug). Two separate
 * defects, both about the step effect NOT re-running — which is why neither is
 * visible reading the JSX:
 *
 *   • Continue — the narration's advance callback runs once per step and
 *     latches. A step that finished while the lesson was held therefore left
 *     nothing scheduled, and releasing the hold changed no state the effect
 *     depends on. The walkthrough sat on that step; the only way on was Next
 *     step, which pauses again.
 *
 *   • Start again — restarting from step 1 sets the index to the value it
 *     already holds, which React treats as no change. The effect never re-ran,
 *     and since restart also wipes the tutor layer the sheet went blank.
 *
 * Driven through the real hook the screen uses, so reverting either fix here
 * fails these tests.
 */

import { act, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/** Narration: capture the onEnd callback so a test can end a step on demand. */
const speakTutor = vi.fn();
vi.mock('@/lib/tts', () => ({
  speakTutor: (text: string, onEnd?: () => void) => speakTutor(text, onEnd),
  stopTutorSpeech: vi.fn(),
}));

import { useWorkedExamplePlayer, type WorkedExamplePlayer } from '@/hooks/useWorkedExamplePlayer';
import type { SchemaWorkedExampleStep } from '@/lib/api';

// Without this React does not treat act() as a flush boundary, so a state
// update made from a timer callback is not applied before the next assertion.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** Mount a hook on its own and keep a live handle on what it returns. */
function renderHook<T>(hook: () => T): { result: () => T; unmount: () => void } {
  let latest: T;
  const root = createRoot(document.createElement('div'));
  act(() => {
    root.render(createElement(() => { latest = hook(); return null; }));
  });
  return { result: () => latest, unmount: () => act(() => root.unmount()) };
}

const STEPS: SchemaWorkedExampleStep[] = [
  { step_id: 'S1', sequence_no: 1, screen_content: '3 + 5 = 8', narration_text: 'Start with three.' },
  { step_id: 'S2', sequence_no: 2, screen_content: '9 + 5 = 14', narration_text: 'Now nine.' },
  { step_id: 'S3', sequence_no: 3, screen_content: 'n + 5', narration_text: 'In general, n.' },
];

/** End the narration that is currently playing. */
function finishNarration(): void {
  const onEnd = speakTutor.mock.calls.at(-1)?.[1];
  act(() => { onEnd?.(); });
}

describe('worked-example walkthrough controls', () => {
  let player: () => WorkedExamplePlayer;
  let drawn: string[];
  let cleared: number;
  let unmount: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    speakTutor.mockReset();
    drawn = [];
    cleared = 0;
    const rendered = renderHook(() =>
      useWorkedExamplePlayer({
        exampleId: 'WE-T01-001',
        steps: STEPS,
        draw: (step) => { drawn.push(step.step_id); },
        onClear: () => { cleared += 1; },
      }),
    );
    player = rendered.result;
    unmount = rendered.unmount;
    // The player waits on a clean sheet before writing the first step.
    act(() => { vi.advanceTimersByTime(500); });
  });

  afterEach(() => {
    unmount();
    vi.useRealTimers();
  });

  /** The step last written to the sheet. */
  const onSheet = () => drawn.at(-1) ?? null;

  it('clears the sheet and writes the first step on arrival', () => {
    expect(cleared).toBeGreaterThan(0);
    expect(onSheet()).toBe('S1');
  });

  it('advances by itself when a narration ends', () => {
    finishNarration();
    act(() => { vi.advanceTimersByTime(450); });
    expect(onSheet()).toBe('S2');
  });

  it('resumes the walkthrough when Continue is pressed after a pause', () => {
    // Hold on step 1, then let its narration finish while held. The advance
    // callback latches here — this is the state the old build could not leave.
    act(() => player().setPaused(true));
    finishNarration();
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(onSheet()).toBe('S1'); // held, correctly

    act(() => player().setPaused(false));
    act(() => { vi.advanceTimersByTime(450); });
    expect(onSheet()).toBe('S2');
  });

  it('keeps holding on Continue while the narration is still speaking', () => {
    // Releasing the hold must not skip a step the student is still hearing.
    act(() => player().setPaused(true));
    act(() => player().setPaused(false));
    act(() => { vi.advanceTimersByTime(2_000); });
    expect(onSheet()).toBe('S1');

    finishNarration();
    act(() => { vi.advanceTimersByTime(450); });
    expect(onSheet()).toBe('S2');
  });

  it('replays the first step when restarted while already on it', () => {
    expect(onSheet()).toBe('S1');
    const before = drawn.length;
    act(() => player().restart());
    act(() => { vi.advanceTimersByTime(500); });
    // Re-written, not merely left alone: restart wipes the sheet first.
    expect(drawn.length).toBeGreaterThan(before);
    expect(onSheet()).toBe('S1');
  });

  it('restarts and keeps running after the student had paused', () => {
    act(() => player().setPaused(true));
    finishNarration();
    act(() => player().restart());
    act(() => { vi.advanceTimersByTime(500); });
    expect(onSheet()).toBe('S1');
    expect(player().paused).toBe(false);

    // The hold is released, so the walkthrough carries on by itself.
    finishNarration();
    act(() => { vi.advanceTimersByTime(450); });
    expect(onSheet()).toBe('S2');
  });

  it('restarts from a later step', () => {
    act(() => player().stepBy(1));
    act(() => { vi.advanceTimersByTime(50); });
    expect(onSheet()).toBe('S2');

    act(() => player().restart());
    act(() => { vi.advanceTimersByTime(500); });
    expect(onSheet()).toBe('S1');
  });

  it('stops advancing by itself once the student steps by hand', () => {
    act(() => player().stepBy(1));
    expect(player().paused).toBe(true);
  });

  it('jumps to the closing message when the walkthrough is skipped', () => {
    act(() => player().skip());
    expect(player().finished).toBe(true);
    expect(player().current).toBeNull();
  });
});
