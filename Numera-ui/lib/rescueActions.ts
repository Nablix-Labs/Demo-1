/**
 * Canvas rescue presentation — the renderer's half of the 22 Aug handoff.
 *
 * The two bottom rungs of the support ladder (PARALLEL_EXAMPLE, TUTOR_SOLVED)
 * used to arrive whole, in `guided_rescue`: every worked step and the final
 * answer in one payload, with RescueNote deciding locally how much of it the
 * student had earned. That contract is inverted here. Chirudeva now owns rescue
 * state, sends exactly ONE authored step per turn, and the renderer is
 * forbidden from deriving later steps or advancing on its own.
 *
 * The inversion is the point, not a refactor. When the client held all the
 * steps, "how much may the student see" was a client guess, and the answer was
 * sitting in the browser the whole time. Now the client cannot show step 3
 * because it has never been told step 3.
 *
 * Both paths exist at once, deliberately. `guided_rescue` is still live on the
 * VM and is what a session falls back to when the presentation flag is off, so
 * removing RescueNote would take the rungs away from every deployment that has
 * not enabled this yet. See lib/guidedRescue.ts for that path.
 */

import type { TutorCanvasAction } from '@/store/useNumeraStore';

export type RescuePresentationMode = 'PARALLEL' | 'TUTOR_SOLVED';

/**
 * One authored rescue step, as the renderer needs it.
 *
 * Every field is derived from the action; nothing is inferred about steps that
 * have not arrived. `totalSteps` is display-only ("2 of 3") — it must never be
 * used to decide what may be shown, because the step that may be shown is the
 * one that was sent.
 */
export interface RescueStep {
  actionId: string;
  rescueId: string;
  mode: RescuePresentationMode;
  stepIndex: number;
  /**
   * Display-only, and NULLABLE. Null means the backend did not say.
   *
   * It must never be defaulted to the current index. Doing that made an
   * unknown total read as "this is the last step": the panel swapped Next
   * for "Return to original" and captioned it "Step 2 of 2", cutting the
   * student off from the rest of a walkthrough while asserting it finished.
   */
  totalSteps: number | null;
  text: string;
  /** The local anchor this step's mark hangs off. */
  anchorId: string;
  /** Where "Return to original" sends focus. Null when the backend omitted it. */
  returnTargetObjectId: string | null;
  /** Whether this step's text may be presented as an answer. Re-derived, not trusted. */
  answerReveal: boolean;
  sourceId: string | null;
}

/**
 * The anchor a rescue step is registered under.
 *
 * Format fixed by the handoff (§4). Built here rather than at each call site so
 * the string that `resolveTarget` matches and the string the acknowledgement
 * reports can never drift apart — they are the same function.
 */
export function rescueAnchorId(rescueId: string, stepIndex: number): string {
  return `TUTOR_ANCHOR:RESCUE:${rescueId}:STEP:${stepIndex}`;
}

/** Parse a rescue anchor id back out. Null when it is some other anchor. */
export function parseRescueAnchor(
  id: string,
): { rescueId: string; stepIndex: number } | null {
  const match = id.match(/^TUTOR_ANCHOR:RESCUE:(.+):STEP:(\d+)$/);
  if (!match) return null;
  const stepIndex = Number(match[2]);
  if (!Number.isInteger(stepIndex) || stepIndex < 1) return null;
  return { rescueId: match[1], stepIndex };
}

/** The two action types that carry a rescue step. */
export function isRescueAction(action: TutorCanvasAction): boolean {
  return action.type === 'SHOW_PARALLEL' || action.type === 'TUTOR_SOLVED_STEP';
}

/**
 * May this action's text be presented as an answer?
 *
 * The handoff states five conditions, and the renderer is the last gate before
 * a student sees a solved answer — so `answer_reveal_allowed: true` is treated
 * as a REQUEST to reveal, re-checked here, not as permission already granted.
 *
 * Three of the five are checkable from the frame and are enforced:
 *   1. type is TUTOR_SOLVED_STEP
 *   2. the presentation is TUTOR_SOLVED
 *   3. it is the final authored step (step_index === total_steps)
 *
 * The other two — that Chirudeva supplied `approved_answer_reveal: true`, and
 * that `text` is exactly the authorised `current_step_text` — are facts about
 * state this process cannot see, and no amount of client checking can
 * establish them. They stay Chirudeva's to guarantee. What this function does
 * is make it impossible for a mis-typed or replayed action to reveal an answer
 * on a rung, a mode or a step where an answer was never authorised, which is
 * the failure the client CAN prevent.
 */
export function answerRevealPermitted(action: TutorCanvasAction): boolean {
  if (action.answer_reveal_allowed !== true) return false;
  if (action.type !== 'TUTOR_SOLVED_STEP') return false;
  if (action.presentation_mode !== 'TUTOR_SOLVED') return false;
  const step = action.step_index;
  const total = action.total_steps;
  if (!Number.isInteger(step) || !Number.isInteger(total)) return false;
  return step === total;
}

/**
 * The mode a rescue action is in, or null when it refuses to say consistently.
 *
 * Mode follows the action type when the backend omits presentation_mode: the
 * two carry the same fact, and the type is the one the switch already keys
 * off. A mode that CONTRADICTS the type is refused instead — that is drift,
 * and guessing which of the two is right is how a tutor-solved answer ends up
 * rendered as a parallel example, or a worked answer lands on the student's
 * page under the wrong heading.
 *
 * One derivation, deliberately. Both `rescueStep` and `writesToStudentCanvas`
 * turn on this decision, and two copies of it that must agree is a copy too
 * many.
 */
function rescueMode(action: TutorCanvasAction): RescuePresentationMode | null {
  const expected: RescuePresentationMode =
    action.type === 'SHOW_PARALLEL' ? 'PARALLEL' : 'TUTOR_SOLVED';
  if (action.presentation_mode && action.presentation_mode !== expected) return null;
  return expected;
}

/**
 * Does this rescue step belong on the student's own canvas?
 *
 * Only TUTOR_SOLVED does, and the distinction is Sanya's, not a nicety
 * (rescue handoff, item 3): tutor-solved is "add each authorised worked step
 * without overwriting the child's writing" — the tutor working through the
 * student's OWN problem beside them — while a parallel example is "a split
 * view between the original question and similar example", because it is a
 * DIFFERENT problem.
 *
 * Writing a parallel example onto the canvas therefore puts another question's
 * working across the page the student is answering on. Seen on 31 Aug with the
 * presentation flag on: three lines of `2x + 4 = 10` sprawled over the working
 * area for `3x + 6 = 18`, which is the one thing both halves of item 3 are
 * written to prevent.
 *
 * Mode comes from `rescueMode`, the same derivation `rescueStep` uses, refusal
 * on a contradicting mode included — if type and mode ever disagree the step is
 * drawn nowhere, because guessing wrong here means an answer landing on the
 * student's page under the wrong heading.
 */
export function writesToStudentCanvas(action: TutorCanvasAction): boolean {
  if (!isRescueAction(action)) return false;
  return rescueMode(action) === 'TUTOR_SOLVED';
}

/**
 * Normalise a rescue action into a step, or null when it is unusable.
 *
 * Null rather than a throw, and null rather than a partial step. A rescue
 * action with no `rescue_id` cannot be acknowledged, advanced or superseded —
 * rendering its text anyway would put content on screen that no subsequent
 * event could ever refer to, which is worse than the rung appearing to have
 * done nothing. Backend fields go missing here without notice, so every read is
 * defensive by default.
 */
export function rescueStep(action: TutorCanvasAction): RescueStep | null {
  if (!isRescueAction(action)) return null;

  const rescueId = action.rescue_id?.trim();
  if (!rescueId) return null;

  const text = action.text?.trim();
  if (!text) return null;

  const stepIndex = action.step_index;
  if (!Number.isInteger(stepIndex) || (stepIndex as number) < 1) return null;

  const mode = rescueMode(action);
  if (!mode) return null;

  // Unknown total: show the step, hide the counter. "Step 2" alone is honest;
  // "step 2 of 0" is not — and neither is silently calling it the last one.
  const rawTotal = action.total_steps;
  const totalSteps = Number.isInteger(rawTotal) && (rawTotal as number) >= (stepIndex as number)
    ? (rawTotal as number)
    : null;

  return {
    actionId: action.action_id,
    rescueId,
    mode,
    stepIndex: stepIndex as number,
    totalSteps,
    text,
    anchorId: rescueAnchorId(rescueId, stepIndex as number),
    returnTargetObjectId: action.return_target_object_id?.trim() || null,
    answerReveal: answerRevealPermitted(action),
    sourceId: action.source_id?.trim() || null,
  };
}

/** Is this the last authored step of its rescue? */
export function isFinalStep(step: RescueStep): boolean {
  // Unknown total is NOT final. A walkthrough whose length the backend did not
  // state stays open, because the alternative — ending it early — takes the
  // remaining steps away from a student who is already stuck.
  return step.totalSteps !== null && step.stepIndex >= step.totalSteps;
}

/**
 * Merge an arriving step into the steps already on screen.
 *
 * Appended in step order, and a re-delivered step index REPLACES rather than
 * duplicates: a reconnect re-sends the current step, and a walkthrough that
 * reads "1, 2, 2, 3" is a rendering artefact the student has to see past.
 *
 * A step belonging to a different rescue starts the list over. Two rescues are
 * never on screen together — the second one replaced the first upstream, and
 * interleaving their steps would read as one incoherent explanation.
 */
export function mergeStep(existing: readonly RescueStep[], incoming: RescueStep): RescueStep[] {
  const sameRescue = existing.filter((s) => s.rescueId === incoming.rescueId);
  const without = sameRescue.filter((s) => s.stepIndex !== incoming.stepIndex);
  return [...without, incoming].sort((a, b) => a.stepIndex - b.stepIndex);
}
