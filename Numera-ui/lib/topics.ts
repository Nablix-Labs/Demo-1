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
