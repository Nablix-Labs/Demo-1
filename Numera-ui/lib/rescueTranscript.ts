/**
 * What the chat is allowed to say on the turn a rescue opens.
 *
 * One learner turn had been producing up to three tutor bubbles: the
 * phase-change line, the authorised hint, and the tutor's own reply — each
 * added by a different rule, each defensible on its own, and all three landing
 * together on the turn where the student is most stuck. On a rescue turn the
 * hint is worse than redundant: it is the rung the rescue was escalated PAST,
 * so the chat ends up coaching the student through the question while the panel
 * beside it works the question for them.
 *
 * Chirudeva, 4 Sep: "Each learner turn should result in one child-facing tutor
 * transcript message; rescue content belongs in the rescue canvas/panel."
 *
 * Scoped to rescue turns on purpose. Collapsing every turn everywhere to one
 * bubble is a bigger change than the report asks for — it would alter hint
 * delivery and phase announcements across the diagnostic and orientation too,
 * neither of which anyone has complained about.
 *
 * The step text is not in scope here for the simple reason that it was never in
 * the transcript: rescue steps reach the student through the panel, the canvas
 * and (as of this work) the tutor's voice, and no code path has ever written
 * one into the chat. What DID reach the chat is `support_message` — the raw
 * authored support behind the rescue — which is what this shuts off.
 */

import { rescueStep } from '@/lib/rescueActions';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

/**
 * Does this reply open or advance a rescue?
 *
 * Judged on whether an action would actually RENDER as a step — the same
 * `rescueStep` the store uses — not on the action type alone. An action with no
 * `rescue_id` puts no panel on screen, so a turn carrying only malformed rescue
 * actions is an ordinary turn and must keep its ordinary chat: suppressing the
 * hint there would take away the last support the student was given and replace
 * it with nothing at all.
 */
export function opensRescue(
  response: { tutor_canvas_actions?: TutorCanvasAction[] | null } | null | undefined,
): boolean {
  const actions = response?.tutor_canvas_actions ?? [];
  return actions.some((action) => rescueStep(action) !== null);
}
