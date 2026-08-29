/**
 * Recovering a question's options when the reply that served it could not
 * carry them.
 *
 * Options never travel on an interaction reply. They live on the session
 * record's question set and are looked up out of it by question id
 * (studentViewFor), so the record has to hold the set the question came from.
 *
 * In Phase 3 it cannot. Silent mode strips `student_model_event` from every
 * interaction reply — `student_model_event=None if phase3_silent else ...`,
 * interaction_service.py:2106 — and that field is the ONLY carrier of a
 * refreshed question set (lib/sessionRecordRefresh.ts). So the moment Phase 3
 * serves a fresh question, which is exactly what a wrong independent attempt
 * triggers (FRESH_INDEPENDENT_QUESTION_REQUESTED, interaction_service.py:792),
 * the cached record still holds the PREVIOUS question, the lookup finds
 * nothing, and the student gets "Which statement correctly describes n + 6?"
 * with no statements under it. Manjusha, 29 Aug: "No option".
 *
 * The strip is deliberate and correct — the event carries tutor_view, which
 * holds the answer — so the repair is not to unstrip it. GET /session/{id} is
 * a different response model that re-declares the field as the PUBLIC event
 * (`student_model_event: PublicStudentModelEvent | None`, models/session.py:316)
 * and serves it in every phase, answers already removed. Re-fetching the
 * record is therefore the whole fix, and it needs nothing from the backend.
 */

import type { QuestionType, SchemaQuestionOption } from '@/lib/api';

/** Question types that are unanswerable without their options on screen. */
const CHOICE_TYPES = new Set<QuestionType>([
  'SINGLE_CHOICE',
  'CHOICE_WITH_EXPLANATION',
  'TRUE_FALSE_WITH_EXPLANATION',
]);

/**
 * Is this question missing options it cannot be answered without?
 *
 * Deliberately narrow. A question whose type is unknown is NOT repaired: the
 * type is not stripped in silent mode, so a null one means the backend really
 * did not say, and re-fetching the record on every free-response question
 * would put a request on the wire for every turn of every phase.
 */
export function optionsMissing(
  questionType: QuestionType | null | undefined,
  options: readonly SchemaQuestionOption[] | null | undefined,
): boolean {
  if (!questionType || !CHOICE_TYPES.has(questionType)) return false;
  return (options?.length ?? 0) === 0;
}
