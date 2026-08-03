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
  if (/\r?\n/.test(t)) return false; // a stack of cases is not one equation
  // Must state a relation, and carry no words — single letters are variables.
  return /[=<>≤≥]/.test(t) && !/[A-Za-z]{2,}/.test(t);
}

/** True when a line is pure maths — no prose words. Single letters are variables. */
function isMathsLine(line: string): boolean {
  return line.trim().length > 0 && !/[A-Za-z]{2,}/.test(line);
}

export type QuestionLayout =
  /** A bare equation: gets the "Solve for x:" lead-in and maths type. */
  | { kind: 'equation'; text: string }
  /**
   * A stack of worked cases, one per line, split into columns.
   *
   * `rows[i][j]` is column j of case i, so the renderer can align them into a
   * grid — which is the whole point. §3 of the Phase 2 spec: "The alignment
   * itself should reveal that the left values change while +5 remains fixed."
   * Read as one wrapped line, the question teaches nothing.
   */
  | { kind: 'cases'; rows: string[][] }
  /** Anything with its own wording. Shown verbatim, line breaks preserved. */
  | { kind: 'prose'; text: string };

/**
 * How to lay out the current question.
 *
 * The line-break case is why this exists. A guided-practice question is often
 * several cases meant to be read down a column:
 *
 *     3 + 5
 *     9 + 5
 *    14 + 5
 *
 * Every screen rendered that inside a `<p>`, where CSS collapses newlines to
 * spaces — so it arrived on the canvas as "3 + 5 9 + 5 14 + 5" and the
 * comparison the question is built around was invisible (Manjusha, 2 Aug 2026).
 * The backend was sending it correctly; the frontend was flattening it.
 *
 * Columns are derived by splitting each line on whitespace rather than trusting
 * the sender to pad with spaces, so alignment holds in a proportional font and
 * does not depend on the backend formatting anything.
 */
export function questionLayout(question: string): QuestionLayout {
  const text = question.trim();
  if (!text) return { kind: 'prose', text: '' };

  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

  if (lines.length > 1 && lines.every(isMathsLine)) {
    const rows = lines.map((l) => l.split(/\s+/));
    // Ragged rows can't be aligned into a grid honestly — fall back to showing
    // the text as sent rather than inventing a column that isn't there.
    const width = rows[0].length;
    if (rows.every((r) => r.length === width)) return { kind: 'cases', rows };
  }

  if (isBareEquation(text)) return { kind: 'equation', text };
  return { kind: 'prose', text };
}
