/**
 * How to present the current question.
 *
 * The backend serves whatever the question is for the phase, and that is not
 * always an equation — a guided-practice question can be a word problem ("a box
 * starts with four counters and receives 5 more, how would you write that as an
 * equation?"). Those two need different typography: an equation wants maths type
 * on one line with a "Solve for x:" lead-in; prose wants a readable font that
 * wraps. Screens used to hard-code the lead-in and the maths font, so a word
 * problem rendered as "Solve for x: a box starts with four…" in a serif on a
 * single non-wrapping line.
 *
 * The frontend does not author or reword questions — it renders `current_question`
 * verbatim and only decides how it should look.
 */

/**
 * True when the question is a bare equation with no surrounding words, e.g.
 * `x + 4 = 9` — so it needs the "Solve for x:" lead-in supplied around it.
 *
 * A question that already carries its own words ("Solve for x: x + 4 = 9", or a
 * full word problem) is prose: it is shown exactly as sent, with no lead-in
 * added, because the backend has already said what it wants the student to do.
 */
export function isBareEquation(question: string): boolean {
  const t = question.trim();
  if (!t) return false;
  // Must state a relation, and carry no words — single letters are variables.
  return /[=<>≤≥]/.test(t) && !/[A-Za-z]{2,}/.test(t);
}
