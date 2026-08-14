/**
 * The Phase 1 worked-example walkthrough player.
 *
 * One step is on the sheet at a time. The tutor narrates it, and when the
 * narration finishes the player writes the next one — unless the student has
 * taken the controls, in which case it holds and they drive.
 *
 * This lives apart from the screen because the parts that break are all about
 * WHEN the step effect re-runs, which is invisible in the JSX and impossible to
 * test through it (the test runner has no JSX transform). Both defects behind
 * "Resume and start again not working" (Manjusha, row 44, 11 Aug) were of that
 * kind — see `settled` and `replay` below.
 *
 * The caller owns what a step looks like: `draw` is handed the step and its
 * position and does the writing, so no geometry lives here.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import type { SchemaWorkedExampleStep } from '@/lib/api';

/** Settling time between a narration ending and the next step landing. */
const ADVANCE_MS = 450;
/** Blank-sheet pause before the first step is written. */
const OPENING_MS = 500;
/** Safety net for a speech provider that never calls back at all. */
const NARRATION_FAILSAFE_MS = 15_000;

export interface WorkedExamplePlayer {
  /** The step on the sheet, or null before the first one / after the last. */
  current: SchemaWorkedExampleStep | null;
  /** Position in the walkthrough. -1 before it starts, `steps.length` when done. */
  index: number;
  steps: SchemaWorkedExampleStep[];
  /** True once the last step has been narrated. */
  finished: boolean;
  /** Held by the student — the player will not advance by itself. */
  paused: boolean;
  setPaused: (paused: boolean) => void;
  /** Move by ±1 step. Takes the player off auto-advance. */
  stepBy: (delta: number) => void;
  /** Back to step 1, running again. */
  restart: () => void;
  /** Jump past the remaining steps to the closing message. */
  skip: () => void;
}

export function useWorkedExamplePlayer({
  exampleId,
  steps: unordered,
  draw,
  onClear,
}: {
  exampleId: string;
  steps: SchemaWorkedExampleStep[];
  /** Write this step onto the sheet. Called once per step shown. */
  draw: (step: SchemaWorkedExampleStep, index: number, total: number) => void;
  /** Wipe the tutor layer. Called on arrival, on leaving, and on restart. */
  onClear: () => void;
}): WorkedExamplePlayer {
  const steps = useMemo(
    () => [...unordered].sort((a, b) => a.sequence_no - b.sequence_no),
    [unordered],
  );

  /**
   * The two callbacks are held in refs and deliberately kept OUT of the effect
   * deps below.
   *
   * They are actions — "write this step", "wipe the sheet" — not values the
   * lesson depends on, and a caller that passes an inline arrow re-creates them
   * every render. With `onClear` in the deps the arrival effect re-ran on every
   * render, and its cleanup cancelled the pending auto-advance: the walkthrough
   * stopped dead the first time any other state changed. Only the example and
   * the step position should restart a lesson.
   */
  const drawRef = useRef(draw);
  const clearRef = useRef(onClear);
  useEffect(() => { drawRef.current = draw; clearRef.current = onClear; });

  // -1 = nothing written yet; steps.length = finished.
  const [index, setIndex] = useState(-1);
  const advance = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Paused means "don't advance by yourself" — the student still moves with the
   * step buttons. The walkthrough used to run start to finish with no way to
   * hold it, go back over a step, or replay it (Manjusha, 2026-07-28), which is
   * exactly what a student needs when a step goes past too fast.
   *
   * Mirrored into a ref because the advance callback is created inside the step
   * effect and would otherwise close over a stale value.
   */
  const [paused, setPausedState] = useState(false);
  const pausedRef = useRef(false);

  /**
   * Has the current step's narration already finished?
   *
   * The advance callback runs once per step and latches. A step whose narration
   * ended while the lesson was held therefore left nothing scheduled, and
   * releasing the hold changed no state the step effect depends on — so the
   * walkthrough sat there. Continue looked dead, and the only way on was Next
   * step, which pauses again (row 44).
   */
  const settled = useRef(false);

  /**
   * Bumped to force a replay of the step already showing.
   *
   * Restarting from step 1 sets the index to the value it already holds, which
   * React treats as no change: the effect never re-ran, and because restart also
   * wipes the tutor layer it left the sheet blank (row 44). Keeping this in the
   * effect's deps makes a replay a real change even when the index does not move.
   */
  const [replay, setReplay] = useState(0);

  /**
   * Set the ref FIRST, then the state.
   *
   * Mirroring the ref during render left a window where a narration finishing
   * between the click and the re-render still saw `paused === false` and
   * scheduled the next step — pressing Pause visibly advanced anyway. The ref
   * is what the advance callback reads, so it has to change synchronously.
   */
  const setPaused = useCallback((next: boolean) => {
    pausedRef.current = next;
    if (next && advance.current) clearTimeout(advance.current);
    setPausedState(next);
    // Continue picks up from where the narration stopped. Without this, resuming
    // is only nominal: nothing is speaking and nothing is scheduled.
    if (!next && settled.current) {
      advance.current = setTimeout(() => {
        if (pausedRef.current) return;
        setIndex((n) => n + 1);
      }, ADVANCE_MS);
    }
  }, []);

  // Start on a clean sheet, and never let this phase's marks follow the student
  // into the next one — the tutor layer is global.
  useEffect(() => {
    clearRef.current();
    const kick = setTimeout(() => setIndex(0), OPENING_MS);
    return () => {
      clearTimeout(kick);
      if (advance.current) clearTimeout(advance.current);
      stopTutorSpeech();
      clearRef.current();
    };
  }, [exampleId]);

  useEffect(() => {
    if (index < 0 || index >= steps.length) return;
    const step = steps[index];
    drawRef.current(step, index, steps.length);

    // Move on when the narration finishes. `done` is latched because speakTutor
    // fires onEnd immediately for empty text and the browser-speech fallback can
    // fire it more than once; the timeout is the safety net for a provider that
    // never calls back at all, so a silent failure can't strand the lesson.
    let done = false;
    settled.current = false;
    const next = () => {
      if (done) return;
      done = true;
      // Recorded before the pause check: Continue needs to know this step has
      // finished, whether or not it was allowed to advance on its own.
      settled.current = true;
      if (pausedRef.current) return;   // held — the student advances manually
      // Re-check on fire: Pause pressed inside this window would otherwise
      // still land one more step, so the button looked ignored.
      advance.current = setTimeout(() => {
        if (pausedRef.current) return;
        setIndex((n) => n + 1);
      }, ADVANCE_MS);
    };
    speakTutor(step.narration_text ?? '', next);
    const failsafe = setTimeout(next, NARRATION_FAILSAFE_MS);
    return () => clearTimeout(failsafe);
  }, [index, replay, steps, exampleId]);

  /** Jump to a step: stops any narration and any pending auto-advance first. */
  const goTo = useCallback((n: number) => {
    if (advance.current) clearTimeout(advance.current);
    stopTutorSpeech();
    setIndex(Math.max(0, Math.min(n, steps.length - 1)));
  }, [steps.length]);

  // Stepping by hand means the student is driving; don't yank them along.
  const stepBy = useCallback((delta: number) => {
    setPaused(true);
    goTo(index + delta);
  }, [setPaused, goTo, index]);

  const restart = useCallback(() => {
    clearRef.current();
    // Release the hold first: restarting a walkthrough the student had paused
    // would otherwise replay step 1 and stop dead there.
    setPaused(false);
    goTo(0);
    setReplay((n) => n + 1);
  }, [setPaused, goTo]);

  const skip = useCallback(() => {
    stopTutorSpeech();
    setIndex(steps.length);
  }, [steps.length]);

  return {
    current: index >= 0 && index < steps.length ? steps[index] : null,
    index,
    steps,
    finished: index >= steps.length,
    paused,
    setPaused,
    stepBy,
    restart,
    skip,
  };
}
