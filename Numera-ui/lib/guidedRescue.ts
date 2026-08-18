/**
 * The last two rungs of the support ladder.
 *
 * `hint → visual cue → scaffold → parallel example → tutor solved`. The first
 * three have had UI for weeks; these two have been typed in lib/api.ts and
 * rendered nowhere, which is recorded as gap C7 in
 * docs/PHASE2-GUIDED-BACKEND-ASKS.md. So a student who worked all the way down
 * the ladder reached the rungs meant to rescue them and saw nothing — the exact
 * shape of the hint bug from 13 August, at the point where the student is most
 * stuck.
 *
 * The revised handoff asks for them explicitly (frontend §2: render parallel
 * examples and tutor-solved content even when `canvas_draw` is empty) and for
 * "step-by-step parallel/tutor-solved presentation" alongside Chirudeva.
 *
 * STEP BY STEP IS THE POINT, not decoration. A worked solution dumped whole is
 * an answer to read; revealed a step at a time it is a solution to follow, and
 * the student stays in the loop that the ladder exists to keep them in. It also
 * keeps tutor-solved honest as the only answer-reveal rung: the final answer is
 * the last thing shown, after the reasoning, rather than the first thing the eye
 * lands on.
 */

export interface GuidedRescuePayload {
  rescue_type: 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';
  micro_skill_id?: string;
  parallel_example?: {
    parallel_example_id?: string;
    problem: string;
    worked_steps: string[];
    final_answer: string;
  } | null;
  tutor_solved?: {
    explanation: string;
    final_answer: string;
    answer_steps: string[];
  } | null;
}

export interface RescuePresentation {
  kind: 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';
  /** What is being worked, shown before any step. */
  problem: string | null;
  /** Revealed one at a time, in order. */
  steps: string[];
  /** Held back until every step has been seen. */
  finalAnswer: string | null;
}

/**
 * Unpack a rescue into what the card needs, or null when there is nothing to
 * show.
 *
 * Null on an empty payload rather than an empty card: `rescue_type` says which
 * rung the backend reached, but a rung with no content renders as the tutor
 * failing at the moment it promised help. Better to leave the ladder where it
 * was than to open a blank panel.
 */
export function rescuePresentation(
  rescue: GuidedRescuePayload | null | undefined,
): RescuePresentation | null {
  if (!rescue) return null;

  if (rescue.rescue_type === 'PARALLEL_EXAMPLE') {
    const example = rescue.parallel_example;
    const steps = (example?.worked_steps ?? []).map((s) => s.trim()).filter(Boolean);
    if (!steps.length) return null;
    return {
      kind: 'PARALLEL_EXAMPLE',
      problem: example?.problem?.trim() || null,
      steps,
      finalAnswer: example?.final_answer?.trim() || null,
    };
  }

  const solved = rescue.tutor_solved;
  const steps = (solved?.answer_steps ?? []).map((s) => s.trim()).filter(Boolean);
  if (!steps.length) return null;
  return {
    kind: 'TUTOR_SOLVED',
    // The explanation frames the solution, so it takes the problem's place at
    // the top rather than being appended after the answer.
    problem: solved?.explanation?.trim() || null,
    steps,
    finalAnswer: solved?.final_answer?.trim() || null,
  };
}

/**
 * How far through the steps the student can currently see.
 *
 * Clamped at both ends so a stale index — from a rescue that was replaced by a
 * shorter one — can never read past the array and blank the card.
 */
export function visibleSteps(steps: readonly string[], revealed: number): string[] {
  return steps.slice(0, Math.max(0, Math.min(revealed, steps.length)));
}

/** Whether every step has been revealed, which is when the answer may show. */
export function fullyRevealed(steps: readonly string[], revealed: number): boolean {
  return steps.length > 0 && revealed >= steps.length;
}
