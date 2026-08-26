/**
 * The turn where the tutor could not read the student, and says so.
 *
 * The reliability gate (revised handoff, Chirudeva §3) is what stops a bad
 * transcript or an unreadable bit of OCR becoming a learning judgement. When
 * voice or OCR confidence is too low the backend returns
 * `requires_written_math_evidence: true` and `next_expected_input: "WRITE"`, and
 * — this is the part that matters pedagogically — it does NOT increment
 * attempts, create an error or misconception event, advance progress, or
 * escalate support. Nothing about the student's understanding has been
 * established, because nothing was actually read.
 *
 * The frontend's obligation is the mirror of that: show the instruction to write
 * or type, do not auto-submit anything, and do not count it against the student
 * locally. A silent WRITE turn is the worst outcome available — the student sat
 * through a turn where the tutor learned nothing and told them nothing, and the
 * natural reading is that they were ignored.
 *
 * The wording is the backend's when it sends one, because it can say WHY
 * ("I couldn't quite catch that" reads differently from "I couldn't read the
 * board"). `WRITE_FALLBACK_PROMPT` is used only when it sends none.
 */

/** The handoff's own suggested wording (revised, frontend §5). */
export const WRITE_FALLBACK_PROMPT = 'Write the rule on the canvas or type it below.';

export interface WrittenEvidenceFields {
  next_expected_input?: string | null;
  requires_written_math_evidence?: boolean | null;
  /** Backend-authored instruction, preferred over the fallback when present. */
  write_instruction?: string | null;
  /** The conversational reply, used as the instruction when it IS one. */
  message?: string | null;
}

/**
 * Is the student being asked to commit this answer in writing?
 *
 * Either field alone is enough. They travel together today, but they are
 * separately meaningful — `next_expected_input` says what to do next, and
 * `requires_written_math_evidence` says why — and a turn that sets one without
 * the other still means the tutor cannot accept spoken maths for this step.
 * Treating that as an ordinary turn would drop the instruction entirely.
 */
export function requiresWriting(response: WrittenEvidenceFields): boolean {
  if (response.requires_written_math_evidence === true) return true;
  return response.next_expected_input?.trim().toUpperCase() === 'WRITE';
}

/**
 * The instruction to put on screen, or null when this is not a WRITE turn.
 *
 * Never returns the tutor's `message` — that is already being spoken and shown
 * in the transcript, and repeating it in the prompt says the same sentence
 * twice. The prompt exists to state the ACTION, which the message may not.
 */
export function writePrompt(response: WrittenEvidenceFields): string | null {
  if (!requiresWriting(response)) return null;
  return response.write_instruction?.trim() || WRITE_FALLBACK_PROMPT;
}
