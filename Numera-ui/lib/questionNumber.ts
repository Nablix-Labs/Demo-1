/**
 * The number shown on the question badge.
 *
 * The backend reports `question_number` on the session record, and for the first
 * question of a phase it is one too high — it renders "2" on the question a
 * student has only just been given.
 *
 * The cause is in `session_service.py`. `_apply_schema_event` first writes the
 * correct value, taken from the question's position in the served set:
 *
 *     updates.update(question_updates)          # question_number = index + 1
 *
 * and then, when the question id has changed, OVERWRITES it with a running
 * increment:
 *
 *     if next_question_id != session.question_id:
 *         updates.update({"question_number": session.question_number + 1, ...})
 *
 * Entering a phase changes the question id, so the increment fires on the first
 * question of the set and turns a correct 1 into 2. Reported to the backend
 * owners; this is the display-side mitigation until it lands.
 *
 * The position is NOT invented here. It is read from the served question set
 * with `questionProgress`, which is the same rule the backend's own
 * `question_index + 1` uses — so this agrees with the backend's intent, and
 * disagrees only with its arithmetic. When the set is not available we fall
 * back to whatever the backend reported rather than guessing.
 */

import { questionProgress, type SessionRecord } from '@/lib/api';

/**
 * Returns the number to show, or null when nothing true can be shown.
 *
 * Null rather than 0: a badge reading "0" is a claim about which question the
 * student is on, and it is never a true one.
 */
export function displayedQuestionNumber(
  record: SessionRecord | null | undefined,
  questionId: string | null | undefined,
  reported: number | null | undefined,
): number | null {
  const { index, total } = questionProgress(record, questionId);
  if (total > 0) return index + 1;
  return reported && reported > 0 ? reported : null;
}
