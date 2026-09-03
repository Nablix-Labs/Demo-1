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
/**
 * The backend's verdict on an independent attempt (PR #105, 11 Aug 2026).
 *
 * Only two of the four are terminal. AWAITING_SUBMISSION means nothing has been
 * handed in yet, and INPUT_UNCLEAR means it was handed in but could not be read
 * — neither closes the attempt, so neither may lock the student's work.
 *
 * The legacy CORRECT/INCORRECT spellings are kept alongside because which one
 * arrives depends on which backend build is deployed, and a tester on the older
 * one must not silently lose the rescue notice.
 */
export type IndependentOutcome =
  | 'AWAITING_SUBMISSION'
  | 'INPUT_UNCLEAR'
  | 'INDEPENDENTLY_VERIFIED'
  | 'RESCUE_REQUIRED'
  | 'CORRECT'
  | 'INCORRECT';

/** The outcomes that mean the attempt is over and may not be answered again. */
const TERMINAL_OUTCOMES = new Set<string>([
  'INDEPENDENTLY_VERIFIED',
  'RESCUE_REQUIRED',
  'CORRECT',
  'INCORRECT',
]);

/** The outcomes that mean a rescue is coming rather than the answer standing. */
const RESCUE_OUTCOMES = new Set<string>(['RESCUE_REQUIRED', 'INCORRECT']);

export interface Phase3ResponseFields {
  /** Terminal verdict for the attempt. Never rendered — see phase3Notice. */
  independent_outcome?: IndependentOutcome | string | null;
  independent_success?: boolean | null;
  /** True once the attempt is closed and cannot be answered again. */
  independent_attempt_terminal?: boolean | null;
  phase3_submission_confirmed?: boolean | null;
  phase3_submission_kind?: 'CANVAS' | 'CHOICE' | null;
  /** Turn-level status; CLARIFICATION_REQUIRED means the OCR was unreadable. */
  status?: string;
  question_id?: string | null;
  /**
   * The question the backend actually graded and locked.
   *
   * Read this rather than the client's own idea of the active question. On
   * 12 Aug 2026 a live payload carried `question_id: "Q-T01-005"` alongside
   * `phase3_locked_question_id: "Q-T01-007"` — the attempt was graded against a
   * different question than the one on screen. Locking the active id there
   * freezes the wrong question and leaves the graded one open.
   */
  phase3_locked_question_id?: string | null;
}

/**
 * Which question this reply's lock belongs to.
 *
 * The backend is authoritative when it names one; the active question is only a
 * fallback for builds that don't send the field yet.
 */
export function phase3LockTarget(
  res: Phase3ResponseFields | null | undefined,
  activeQuestionId: string | null,
): string | null {
  const named = res?.phase3_locked_question_id?.trim();
  if (named) return named;
  return activeQuestionId;
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
  // The outcome enum says this outright, and it outranks the flags beside it:
  // an unreadable or not-yet-made submission leaves the attempt open however
  // `independent_attempt_terminal` and `phase3_submission_confirmed` were set.
  const outcome = res.independent_outcome;
  if (outcome === 'INPUT_UNCLEAR' || outcome === 'AWAITING_SUBMISSION') return false;
  if (typeof outcome === 'string' && TERMINAL_OUTCOMES.has(outcome)) return true;
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
  const outcome = res?.independent_outcome;
  if (res?.status === 'CLARIFICATION_REQUIRED' || outcome === 'INPUT_UNCLEAR') return OCR_UNCLEAR;
  // All four outcomes are handled explicitly rather than leaning on
  // `independent_success`, so that a build which sends the enum and omits the
  // boolean still gets the rescue line right.
  const failed =
    (typeof outcome === 'string' && RESCUE_OUTCOMES.has(outcome))
    || (outcome == null && res?.independent_success === false);
  return failed ? RESCUE_PENDING : ANSWER_RECORDED;
}

/**
 * Has the backend said REVIEW is where the student goes next?
 *
 * `recommended_entry_phase` rides on every interaction reply and is NOT
 * stripped in silent mode (interaction_service.py:2104) — it is the Student
 * Model's own answer to "where does this student belong now", carried through
 * as `PHASE_FROM_STUDENT_MODEL[journey_state.recommended_entry_phase]`. It has
 * been typed on InteractionResponse and read by nothing.
 *
 * Reading it is what closes Phase 3 by itself. Until now the last independent
 * attempt locked the canvas, said "Answer recorded." and stopped: the student
 * had to notice "Review with tutor" and press it to reach the review they had
 * just earned (Manjusha, 29 Aug — "It doesn't take me to review page
 * automatically when the inde practice is completed").
 *
 * Paired with `servedNextQuestion` at the call site, never alone. Acting on
 * this field while a fresh question is arriving would end a session the
 * student is still working in, and ending a session is not undoable.
 *
 * ── Why both fields, not just the recommendation (3 Sep 2026) ──────────────
 * This read `recommended_entry_phase` alone, which is a recommendation about
 * where the student belongs NEXT. But a completed Phase 3 is answered by
 * `/canvas/submit` with `current_phase: "REVIEW"` and no recommendation at
 * all — the backend has already moved them, so it recommends nothing. So the
 * one reply that means "Phase 3 is over" returned false here: the auto-exit
 * never fired and the canvas locked on "Answer recorded." with nothing to
 * press. Either field naming REVIEW is the backend saying review is next; the
 * recommendation is a prediction, the current phase is a fact, and the fact
 * was the half being ignored.
 */
export function reviewIsNext(
  res: {
    current_phase?: string | null;
    recommended_entry_phase?: string | null;
  } | null | undefined,
): boolean {
  const current = res?.current_phase?.trim().toUpperCase();
  const recommended = res?.recommended_entry_phase?.trim().toUpperCase();
  return current === 'REVIEW' || recommended === 'REVIEW';
}

/**
 * Did this reply hand the student a different question to work on?
 *
 * A wrong independent attempt is answered with a FRESH question
 * (interaction_service.py:792), and that reply closes the old attempt exactly
 * like a right one does. So "the attempt is over" cannot mean "practice is
 * over" — this is what tells them apart.
 */
export function servedNextQuestion(
  res: Phase3ResponseFields | null | undefined,
  answeredQuestionId: string | null,
): boolean {
  const served = res?.question_id?.trim();
  if (!served) return false;
  return served !== answeredQuestionId;
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
