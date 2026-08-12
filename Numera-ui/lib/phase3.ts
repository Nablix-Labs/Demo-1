/**
 * Phase 3 — independent practice, in silent mode.
 *
 * Phase 3 is the only phase where the student's answer is taken as evidence of
 * what they can do ALONE. That makes the UI's job the opposite of Phase 2's:
 * everything that would help, hint, correct, or even react has to be off, and
 * an answer that has been accepted must stop being editable — otherwise the
 * evidence is of what the student could do with help, or after seeing how the
 * tutor reacted.
 *
 * The rules (Phase 3 spec, §3 "Numera-ui silent-mode work"):
 *
 *   During an active attempt — canvas work and approved choice selection only.
 *   No hints, visual cues, scaffolds, Explain Again, Need Help, tutor ink or
 *   correction overlays. Voice stays available for accessibility and
 *   clarification but must never submit an independent answer.
 *
 *   After an accepted submission — ink and choices lock immediately, the lock
 *   survives reconnects and duplicate replies, and the only thing shown is one
 *   neutral line. No correctness, no error codes, no answer steps, no support.
 *
 *   When a rescue or fresh question arrives — it is shown as a NEW question,
 *   not as feedback on the closed one, and the lock lifts only for that new
 *   question id.
 *
 * The lock is keyed by question id rather than a boolean for that last rule:
 * "clear the previous lock only for the new question ID" is then a comparison
 * rather than a sequence of events that a duplicate reply could replay.
 */

export const PHASE_3 = 'INDEPENDENT_PRACTICE';

/** Aliases the backend has used for the same phase. */
const PHASE_3_ALIASES = new Set([PHASE_3, 'PHASE_3_INDEPENDENT_PRACTICE', 'INDEPENDENT']);

export function isPhase3(phase: string | null | undefined): boolean {
  return phase !== null && phase !== undefined && PHASE_3_ALIASES.has(phase.trim().toUpperCase());
}

/**
 * Phase 3 fields on an interaction reply.
 *
 * All optional: the backend work that emits them (spec §1) is not shipped yet,
 * and everything here degrades to the safest reading when they are absent —
 * which for a phase built on "say nothing" means saying nothing.
 */
export interface Phase3ResponseFields {
  /** Terminal verdict for the attempt. Never rendered — see phase3Notice. */
  independent_outcome?: string | null;
  independent_success?: boolean | null;
  /** True once the attempt is closed and cannot be answered again. */
  independent_attempt_terminal?: boolean | null;
  phase3_submission_confirmed?: boolean | null;
  phase3_submission_kind?: 'CANVAS' | 'CHOICE' | null;
  /** Turn-level status; CLARIFICATION_REQUIRED means the OCR was unreadable. */
  status?: string;
  question_id?: string | null;
}

/** The only three things Phase 3 may say to a student before REVIEW. */
export const ANSWER_RECORDED = 'Answer recorded.';
export const RESCUE_PENDING = "We'll review this one before a fresh independent check.";
export const OCR_UNCLEAR =
  "I couldn't read that clearly. Your work is still here — try writing it once more.";

/**
 * True when this reply closes the attempt.
 *
 * An unreadable submission explicitly does NOT: "OCR unclear preserves canvas
 * and leaves attempt unlocked", so the student can rewrite it rather than
 * losing an attempt to their handwriting.
 */
export function phase3AttemptClosed(res: Phase3ResponseFields | null | undefined): boolean {
  if (!res) return false;
  if (res.status === 'CLARIFICATION_REQUIRED') return false;
  if (res.independent_attempt_terminal === true) return true;
  // Before the backend sends the terminal flag, a confirmed submission is the
  // only other thing that means "this attempt is over".
  return res.phase3_submission_confirmed === true;
}

/**
 * The single neutral line shown after an attempt closes.
 *
 * Deliberately not derived from anything the student could read as a verdict
 * beyond what the spec allows: a rescue is coming or it isn't. When the backend
 * has said nothing about the outcome, this is the quieter of the two.
 */
export function phase3Notice(res: Phase3ResponseFields | null | undefined): string {
  if (res?.status === 'CLARIFICATION_REQUIRED') return OCR_UNCLEAR;
  // The backend renamed these on 11 Aug 2026: CORRECT/INCORRECT became
  // INDEPENDENTLY_VERIFIED/RESCUE_REQUIRED. Both spellings are accepted so a
  // rescue is still recognised whichever build is deployed, and so this does not
  // rest solely on the boolean beside them.
  const outcome = res?.independent_outcome;
  const failed =
    res?.independent_success === false || outcome === 'INCORRECT' || outcome === 'RESCUE_REQUIRED';
  return failed ? RESCUE_PENDING : ANSWER_RECORDED;
}

/**
 * Is the student's work locked right now?
 *
 * A lock belongs to the question it was taken on. Comparing ids rather than
 * holding a boolean is what makes a duplicate or out-of-order reply harmless:
 * replaying the lock for a question that is no longer active changes nothing,
 * and a rescue question unlocks by virtue of having a different id.
 */
export function phase3Locked(
  lockedQuestionId: string | null,
  activeQuestionId: string | null,
): boolean {
  if (lockedQuestionId === null) return false;
  // A locked attempt with no active question yet (mid-transition) stays locked;
  // unlocking on a null id would hand the canvas back for a moment.
  if (activeQuestionId === null) return true;
  return lockedQuestionId === activeQuestionId;
}
