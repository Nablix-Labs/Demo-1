/**
 * Topics — the ordered sequence the adaptive loop walks through.
 *
 * Derived from the existing CURRICULUM so every flow stage (orientation video,
 * topic diagnostic, workbook) already has content for these ids. The starting
 * topic is NOT fixed: the Main Diagnostic places the student at some Topic N in
 * this list (see lib/flow.ts). N is an output, never a constant.
 *
 * For the demo we walk the first three curriculum topics — enough to show
 * N, N+1 and the skip-orientation path.
 */

import { CURRICULUM } from './curriculum';

export interface Topic {
  id: string;
  name: string;
}

export const TOPICS: Topic[] = CURRICULUM.slice(0, 3).map((t) => ({
  id: t.id,
  name: t.title,
}));

export const topicIndex = (id: string) => TOPICS.findIndex((t) => t.id === id);
export const topicById = (id: string) => TOPICS.find((t) => t.id === id);

/** The next topic in sequence, or null if this is the last one. */
export const nextTopicId = (id: string): string | null => {
  const i = topicIndex(id);
  return i >= 0 && i + 1 < TOPICS.length ? TOPICS[i + 1].id : null;
};

/**
 * The topic code to send on a session start, or undefined to let the backend
 * choose. A real student's currentTopicId is a backend code (ALG-ORI-03) set
 * by a hand-off or by login; the local table's ids (algebra, number, …) are
 * mock-mode only and must never reach /session/start — the Student Model
 * rejects them as UNKNOWN_TOPIC. Without this the Lesson and Practice tabs
 * opened the hard-coded default concept, which for a student who has
 * finished it is a 42s review-blocked start that times out (ST015, 21 Sep).
 */
export const liveTopicCode = (currentTopicId: string | null | undefined): string | undefined => {
  const id = currentTopicId?.trim();
  if (!id || topicById(id)) return undefined;
  return id;
};
