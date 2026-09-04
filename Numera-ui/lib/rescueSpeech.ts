/**
 * Saying the rescue out loud.
 *
 * The rescue rungs have been silent since they shipped. Not a race, not a
 * dropped utterance — there was no `tutorSay` call anywhere on the rescue path
 * at all. So "Let me show you" appeared as a card and the tutor said nothing,
 * at the one moment in the session where the student is most stuck and least
 * able to get going from text alone (Chirudeva, 4 Sep: "the silent 'Let me show
 * you' sequence").
 *
 * Two rules, and the second is the reason this is a module rather than three
 * lines in a component:
 *
 *   EXACTLY ONCE per step, keyed on the action id. Steps re-arrive — a
 *   reconnect re-sends the current one, `mergeStep` replaces rather than
 *   duplicates it, and React re-renders for reasons that have nothing to do
 *   with the tutor. Keying on the step INDEX would not survive a rescue being
 *   superseded (B's step 1 is not A's step 1); keying on the text would not
 *   survive two steps that happen to read the same. The action id is the only
 *   thing that identifies this authored step and no other.
 *
 *   AFTER its visual. `afterMarks` delays the words so the mark lands first —
 *   the tutor draws, then describes what it drew, which is the ordering §1 of
 *   the canvas contract asks for and the one that makes a walkthrough legible.
 *
 * The set is module-level, alongside the render-dedupe windows in the store, for
 * the same reason they are: it is a memory of what has already happened to the
 * student, not state anything renders from.
 */

import type { RescueStep } from '@/lib/rescueActions';

const spoken = new Set<string>();

/**
 * The newest step that has not been spoken yet, or null.
 *
 * Newest rather than oldest-unspoken. If two steps land together — a queued
 * action released by a render, or a reconnect delivering a backlog — the
 * student is looking at the last one, and narrating the one before it would
 * describe a mark that is no longer the subject. The skipped step is marked
 * spoken rather than left pending, so it cannot surface later out of order.
 */
export function nextUnspokenStep(steps: readonly RescueStep[]): RescueStep | null {
  const step = steps[steps.length - 1];
  if (!step || spoken.has(step.actionId)) return null;
  return step;
}

/**
 * Speak a step, once.
 *
 * Marks it spoken BEFORE speaking, not after. `tutorSay` returns false when the
 * student has the floor — they are writing, and §1 says the tutor stays quiet
 * — and that is a decision not to say this step, not a failure to be retried.
 * Retrying it would wait for the pen to lift and then narrate a step the
 * student has already read and possibly already advanced past.
 *
 * Returns whether audio was actually started, for the caller that wants to
 * know; nothing depends on it.
 */
export function speakRescueStep(
  step: RescueStep,
  say: (text: string) => boolean,
): boolean {
  if (spoken.has(step.actionId)) return false;
  spoken.add(step.actionId);
  return say(step.text);
}

/** Has this step already been said? Exposed for tests and for teardown checks. */
export function hasSpokenRescueStep(actionId: string): boolean {
  return spoken.has(actionId);
}

/**
 * Forget everything said.
 *
 * For session teardown and tests only. NOT called when a rescue is cleared: a
 * student who returns to the question and is then served the same rescue again
 * is being shown it a second time deliberately, and re-narrating a step whose
 * id has not changed would mean the backend re-sent an action it had already
 * had acknowledged — which is the replay case this set exists to absorb.
 */
export function forgetSpokenRescueSteps(): void {
  spoken.clear();
}
