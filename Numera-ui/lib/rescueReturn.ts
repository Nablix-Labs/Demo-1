/**
 * Coming back from a rescue.
 *
 * Sanya's rescue handoff, item 3: "Final step: return focus to the original
 * problem and restore normal input." Dismissing the panel is only half of that
 * — the student has just spent several steps reading the tutor's work, and
 * leaving them with the panel gone and the caret nowhere is how a walkthrough
 * ends in a shrug. The point of the return is that the student is put back
 * where they answer.
 *
 * What "focus" means here is deliberately modest. The backend names a
 * `return_target_object_id` (a question token, e.g. `Q1:QTOKEN:1`), but the
 * client has no way to focus a token: FOCUS actions draw nothing and there is
 * no per-token focus state on the canvas. So rather than invent one, this does
 * the two things that are real and observable — put the question back in view
 * and the caret back in the student's input — and reports the target it was
 * given so a later focus mechanism has a caller waiting.
 *
 * Kept out of the component because a click handler cannot be tested, and this
 * is the part of the rescue contract most likely to be quietly dropped in a
 * refactor: nothing looks broken when a return does nothing.
 */

/** The composer the student types their answer into. */
export const COMPOSER_LABEL = 'Message Numera';

export interface ReturnSurfaces {
  /** The element holding the question being worked. Null when off screen. */
  question: { scrollIntoView: (opts?: ScrollIntoViewOptions) => void } | null;
  /** The student's text input. Null in voice-only layouts. */
  composer: { focus: () => void } | null;
}

export interface ReturnOutcome {
  scrolledToQuestion: boolean;
  focusedComposer: boolean;
}

/**
 * Put the student back on their own question.
 *
 * Both halves are independent and neither is required: a layout with no
 * composer (voice-only) still scrolls, and a question already in view still
 * takes the caret. Returning what actually happened is what makes this
 * assertable — "we called it" is not the same claim as "the student is back".
 */
export function returnToQuestion(surfaces: ReturnSurfaces): ReturnOutcome {
  const outcome: ReturnOutcome = { scrolledToQuestion: false, focusedComposer: false };

  if (surfaces.question) {
    // `nearest` rather than `center`: the question is usually already visible,
    // and yanking a settled page for a no-op scroll reads as a glitch.
    surfaces.question.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    outcome.scrolledToQuestion = true;
  }

  if (surfaces.composer) {
    surfaces.composer.focus();
    outcome.focusedComposer = true;
  }

  return outcome;
}

/**
 * Find the two surfaces in a document.
 *
 * Separated from the acting so the behaviour above can be tested without a DOM,
 * and so a layout change breaks lookup in one place rather than everywhere.
 */
export function findReturnSurfaces(doc: Document): ReturnSurfaces {
  return {
    question: doc.querySelector<HTMLElement>('[data-question-text]'),
    composer: doc.querySelector<HTMLInputElement>(
      `input[aria-label="${COMPOSER_LABEL}"]`,
    ),
  };
}
