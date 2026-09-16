/**
 * Rescue as an exclusive MODE, not a card that happens to be on screen.
 *
 * The two rescue implementations grew up independently — `guided_rescue`
 * (whole payload, paced locally by RescueNote) and the stepwise actions
 * (one authored step per turn, RescueSteps) — and SupportLane rendered both,
 * on the written assumption that "the backend serves either one or the other,
 * never both". That assumption is what failed: Chirudeva's 4 Sep report is two
 * panels for one rescue, with the lower rungs still stacked above them.
 *
 * Nothing here is new behaviour on its own. It is the one place that answers
 * "is a rescue running right now", so that the panel, the lane, the speaker,
 * the chat box and the microphone stop each deciding it for themselves. Every
 * disagreement in that report is two of those five answering differently.
 *
 * Stepwise WINS when both have content. It is the contract the backend is
 * moving to, its steps are authored one at a time, and the legacy payload
 * carries every step including the answer — so when the two disagree, showing
 * the legacy one would put the whole solution on screen beside a walkthrough
 * that is deliberately releasing it a step at a time.
 */

import { isPhase3 } from '@/lib/phase3';
import { isFinalStep, type RescueStep } from '@/lib/rescueActions';
import type { GuidedRescuePayload } from '@/lib/guidedRescue';

/**
 * The store fields the mode is derived from.
 *
 * Structural rather than the store type itself, so the rules can be tested on
 * plain objects — and so a call site cannot accidentally widen what "a rescue
 * is active" depends on.
 */
export interface RescueModeState {
  rescueSteps: readonly RescueStep[];
  guidedRescue: GuidedRescuePayload | null;
  currentPhase: string | null;
}

/**
 * Shown while normal input is held back, so a disabled chat box and a mic that
 * sends nothing read as "do this first" rather than as a broken page.
 *
 * Names the control that moves the turn on. "Please wait" would be true and
 * useless — the student is not waiting for anything, they are being asked to
 * read something and then press a specific button.
 */
export const RESCUE_INPUT_NOTICE =
  'Follow this example — the tutor moves on as it finishes. Next step skips ahead.';

/**
 * Is a stepwise rescue running?
 *
 * Phase 3 is answered alone (spec §3.2), so support cannot be active there
 * whatever arrived — the store already refuses to record rescue actions in
 * Phase 3, and this agrees with it rather than trusting that it ran first.
 */
export function rescueActive(state: RescueModeState): boolean {
  if (isPhase3(state.currentPhase)) return false;
  return state.rescueSteps.length > 0;
}

/**
 * May the legacy `guided_rescue` card render?
 *
 * Only when the stepwise path has nothing — "use legacy guided_rescue only if
 * no stepwise action exists". Precedence only: whether the legacy payload has
 * anything worth showing stays RescueNote's own question, because an empty
 * payload must render nothing rather than an empty card (see lib/guidedRescue).
 */
export function legacyRescueVisible(state: RescueModeState): boolean {
  if (isPhase3(state.currentPhase)) return false;
  if (state.rescueSteps.length > 0) return false;
  return state.guidedRescue !== null;
}

/**
 * Does the PANEL carry this step's words, or is the canvas already doing it?
 *
 * One `TUTOR_SOLVED_STEP` action was rendered on two surfaces at once: the
 * store writes `action.text` onto the tutor layer via `actionMarks`
 * (useNumeraStore, the `rescue-slot` branch) AND hands the same text to the
 * panel through `rescueStep`. So the current step appeared as ink on the canvas
 * and again in the sticky note — "its writing twice" (Manjusha, 6 Sep).
 *
 * The split is not new information: `writesToStudentCanvas` already decides
 * which steps reach the page, and `mode` carries the same fact onto the step.
 *
 *   TUTOR_SOLVED — the tutor is working down the student's own page, so the
 *   words are on the canvas. The panel is the control surface: which step this
 *   is, and how to move on.
 *
 *   PARALLEL — a different problem, deliberately never written onto the page
 *   the student is working on. The panel is its only surface, so it must keep
 *   the text; dropping it would leave a card with a step counter and nothing
 *   to read.
 *
 * Keyed off `mode` rather than a new flag so the panel and the canvas cannot
 * disagree about which of them is carrying the words.
 */
export function panelCarriesStepText(step: RescueStep | null | undefined): boolean {
  if (!step) return false;
  return step.mode === 'PARALLEL';
}

/**
 * The step the student is looking at, or null.
 *
 * The last one to arrive, which is the one the backend considers current — the
 * panel shows exactly this one, while the canvas keeps the earlier marks (a
 * tutor-solved rescue IS the tutor working down the page, so the written
 * column accumulates even though the panel does not).
 */
export function currentRescueStep(state: RescueModeState): RescueStep | null {
  if (!rescueActive(state)) return null;
  return state.rescueSteps[state.rescueSteps.length - 1] ?? null;
}

/**
 * Is normal answer submission held back?
 *
 * Separate name from `rescueActive` on purpose, even though the rule is the
 * same today. The call sites are asking a different question — "may this
 * student send an answer" — and a normal `/interaction` answer sent during a
 * rescue is evaluated against the ORIGINAL question, which re-opens the
 * scaffold the rescue was escalated past. If that ever needs to diverge from
 * "a panel is on screen", it diverges here rather than at five call sites.
 */
export function rescueBlocksSubmission(state: RescueModeState): boolean {
  return rescueActive(state);
}

/**
 * A press that is outstanding, or one that failed, and the step it happened on.
 *
 * Both are keyed to the rescue AND the step rather than held as bare flags,
 * which is the only thing that makes them survive the two events that
 * invalidate them: a rescue being superseded, and the step they were about
 * actually arriving.
 */
export interface AdvanceLatch {
  rescueId: string;
  step: number;
}

/**
 * Is the student still waiting for the step they asked for?
 *
 * Outstanding only for THIS rescue, and only until a step at or past the one it
 * asked for arrives. Held as a bare step number it survived into the next
 * rescue — press Next on step 3 of A, A is superseded by B starting at step 1,
 * and B opens with its button already disabled and no way to re-enable it.
 */
export function advancePending(
  awaiting: AdvanceLatch | null,
  current: { rescueId: string; stepIndex: number },
): boolean {
  if (awaiting === null) return false;
  if (awaiting.rescueId !== current.rescueId) return false;
  return awaiting.step > current.stepIndex;
}

/**
 * Did the press on the step now showing fail to reach the backend?
 *
 * Scoped to the exact step for the same reason: held as a bare boolean the
 * notice survived onto the steps that DID arrive, so step 2 rendered with
 * "couldn't ask for the next step" sitting under it — a failure notice attached
 * to a success.
 */
export function advanceFailed(
  failure: AdvanceLatch | null,
  current: { rescueId: string; stepIndex: number },
): boolean {
  if (failure === null) return false;
  return failure.rescueId === current.rescueId && failure.step === current.stepIndex;
}

/**
 * A narrated step that has been heard to the end, and what it was about.
 *
 * `audioStarted` is the half that matters and the half a callback cannot tell
 * you. `tutorSay` calls back whether or not it spoke — it declines the floor
 * while the student is writing, and says nothing at all when audio is muted or
 * has failed — so the callback alone is not evidence the student heard
 * anything. Only `speakRescueStep`'s return value is.
 */
export interface NarratedStep {
  step: RescueStep | null;
  audioStarted: boolean;
  /** How long the utterance actually lasted, start of speech to `onEnd`. */
  narratedMs: number;
}

/**
 * Below this, nothing was really said.
 *
 * `tutorSay` reports that it STARTED, which is not the same as the student
 * having heard anything. The TTS chain ends at browser speech, and on a device
 * with no voices — or with audio blocked before the first gesture — that hands
 * the callback straight back. Taken at face value it would run a whole silent
 * walkthrough past the student in a few hundred milliseconds, which is a worse
 * failure than the button it replaced.
 *
 * Generous on purpose. This is not a reading-time estimate; it only has to
 * separate "spoke" from "returned immediately", and the shortest authored step
 * still takes the better part of a second to say.
 */
export const MIN_NARRATION_MS = 600;

/**
 * Should the tutor finishing a step carry the walkthrough on by itself (#319)?
 *
 * A rescue was reading as a slideshow: every step sat waiting for "Next step",
 * including the ones the tutor had just finished explaining out loud. "The
 * parallel and tutor solved should be displayed like a live tutor is explaining
 * and not like the student should press the next button each time."
 *
 * So the voice paces it. This does NOT advance the view — nothing here does,
 * and that is deliberate: the backend owns the position and the client asks.
 * Answering true means "send RESCUE_STEP_ADVANCE now", exactly as the button
 * does, and the step still arrives from the backend or does not arrive at all.
 *
 * The button stays, and stays live while the tutor is talking. It is how a
 * student skips ahead, and it is the ONLY way forward whenever the tutor could
 * not speak — muted, failed, or silent because the student has the pen (§1).
 * That is why `audioStarted` gates this: advancing on an utterance that never
 * happened would race a silent walkthrough past a student who is reading it.
 *
 * Staleness is checked by identity, not by index. An utterance outlives the
 * step it was about — the student presses Next mid-sentence, or a rescue is
 * superseded — and acting on a finished sentence about a step that is no longer
 * on screen would skip the step that is.
 */
export function narrationAdvances(
  narrated: NarratedStep,
  current: RescueStep | null,
  completed: boolean,
): boolean {
  if (!narrated.audioStarted || !narrated.step || !current) return false;
  // Started is not the same as said; see MIN_NARRATION_MS.
  if (narrated.narratedMs < MIN_NARRATION_MS) return false;
  // The utterance has to be about the step the student is looking at now.
  if (narrated.step.actionId !== current.actionId) return false;
  if (narrated.step.rescueId !== current.rescueId) return false;
  // The last step is where "Return to original" lives; asking past it would
  // request a step the backend has already said does not exist.
  return !isFinalStep(current) && !completed;
}
