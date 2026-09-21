/**
 * What `/session/start` is asked for.
 *
 * Split out because getting it wrong is silent: the backend accepts
 * `topic_code` OR `concept_id`, resolves the latter through
 * `settings.student_model_topic_codes` — a map that holds one entry — and
 * answers 422 when it cannot. So a next topic sent as a concept id simply never
 * starts, which is how the review loop looked from the outside.
 */
import type { InteractionMode, StartSessionPayload } from '@/lib/api';

/**
 * Prefer the topic code. When it is present it IS the topic: no lookup, and a
 * new topic never needs a backend deploy (`session_service.py:502`).
 *
 * The two are never sent together. `concept_id` survives only as the RAG key
 * for the older path, and sending both would leave which one won up to the
 * server rather than to the caller that knows which it has.
 */
export function startPayloadFor(
  studentId: string,
  conceptId: string,
  topicCode: string | null | undefined,
  mode: InteractionMode,
): StartSessionPayload {
  const code = topicCode?.trim();
  if (code) return { student_id: studentId, topic_code: code, interaction_mode: mode };
  return { student_id: studentId, concept_id: conceptId, interaction_mode: mode };
}

/**
 * Did the Student Model reject the topic we named?
 *
 * The tutor backend forwards SESSION_OPENED with our `topic_code`; an id it
 * does not know comes back 404 `UNKNOWN_TOPIC`. That happened with the
 * session's own `concept_id` (`ALG_LINEAR_ONE_STEP`), which the tutor backend
 * accepts as a concept but the Student Model does not know as a topic
 * (ST030, 21 Sep). Starting again WITHOUT the code lets the backend open the
 * journey's current topic itself.
 */
export function unknownTopicRejection(err: unknown): boolean {
  const e = err as { response?: { status?: number; data?: { error_code?: string; message?: string } } };
  const res = e?.response;
  if (res?.status !== 404) return false;
  const body = `${res.data?.error_code ?? ''} ${res.data?.message ?? ''}`;
  return /UNKNOWN_TOPIC/i.test(body);
}
