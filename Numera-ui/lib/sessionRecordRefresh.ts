/**
 * Keeping the cached session record current when the backend issues a new
 * question set.
 *
 * Question OPTIONS do not travel on an interaction reply. They live on the
 * session record and are looked up out of it by question id, so the record has
 * to be refreshed the moment the backend issues a new set — which is what a
 * phase change does. Left stale, the lookup searches the PREVIOUS phase's
 * questions, finds nothing, and the student gets a choice question with no
 * choices under it.
 *
 * That failure was found and fixed on the REST path (Manjusha, 13 Aug 2026) and
 * then reintroduced on the voice path, which re-implements the same sync inline
 * and simply never did this part. Guided Practice is mostly voice-led, so the
 * transport missing it is the transport it matters on.
 *
 * Extracted so there is one implementation rather than two that drift.
 */

import type { StudentModelEvent } from '@/lib/api';

export interface RecordCarrier {
  student_model_event?: StudentModelEvent | null;
}

/**
 * Does this reply carry a question set that supersedes the cached record?
 *
 * Only a set is worth writing: an event without one carries no options, and
 * overwriting the record with it would drop the options already held for the
 * current question.
 */
export function carriesQuestionSet(response: RecordCarrier | null | undefined): boolean {
  return Boolean(response?.student_model_event?.phase_payload?.question_set);
}

/**
 * The record to cache, or null when nothing should change.
 *
 * Null covers both "this reply carries no new set" and "there is no record to
 * merge into" — writing a record built only from an event would replace a full
 * session with a fragment.
 */
export function refreshedRecord<T extends object>(
  current: T | null | undefined,
  response: RecordCarrier | null | undefined,
): T | null {
  if (!current || !carriesQuestionSet(response)) return null;
  return { ...current, student_model_event: response!.student_model_event };
}
