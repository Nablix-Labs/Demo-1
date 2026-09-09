/**
 * A content gap: the authored question does not exist.
 *
 * It is not mastery, not an intervention, and not a transient error, and it has
 * been read as all three. In the ST017 run the client asked for a fresh
 * question twice — journey versions 12 then 13 — because nothing on this side
 * knew to stop. The backend now persists the pause on the first authoritative
 * gap response specifically so that nothing asks again; a client retry loop
 * would reintroduce exactly that.
 *
 * Two shapes, deliberately different:
 *
 *   GET /session   200, with the paused session: `content_gap_detected` set and
 *                  no active question. This is a STATE to render. There is
 *                  nothing to retry.
 *   a submission   409 CONTENT_GAP. The same paused state is shown rather than
 *                  a generic error.
 *
 * Distinct from a terminal intervention, which carries an
 * `intervention_input_request` and DOES expect input from the learner. Here
 * there is nothing to ask for and nobody has been asked.
 */

import type { SessionRecord } from '@/lib/api';

/**
 * Was this submission refused because there is no question to answer?
 *
 * Matched on the code AND the 409, like every other conflict: the same code on
 * a 500 would be a server fault, and pausing the lesson on one would hide it.
 * The backend raises `{"code": "CONTENT_GAP"}` and the app's exception handler
 * lifts that into the `error_code` field the client already reads.
 */
export function isContentGapError(err: unknown): boolean {
  const res = (err as { response?: { status?: number; data?: { error_code?: string } } })?.response;
  return res?.status === 409 && res?.data?.error_code === 'CONTENT_GAP';
}

/**
 * Does this session record describe a topic paused on a content gap?
 *
 * Requires BOTH the flag and the absence of a question. A gap flag alongside a
 * live question is not a pause — the student has something to answer, and
 * blanking the screen would take it away from them.
 *
 * A missing routing block reads as "no gap" rather than throwing or assuming
 * one. Manufacturing a pause out of an absent field would strand a student
 * whose lesson is perfectly fine, which is the more damaging of the two
 * mistakes.
 */
export function contentGapPaused(rec: SessionRecord | undefined | null): boolean {
  if (!rec) return false;
  const routing = (rec.student_model_event as { routing?: { content_gap_detected?: boolean } } | null | undefined)?.routing;
  if (routing?.content_gap_detected !== true) return false;
  return !rec.question_id;
}
