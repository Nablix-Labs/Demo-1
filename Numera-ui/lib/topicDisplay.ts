/**
 * The name and id to render for a topic, for any topic id the app is given.
 *
 * `getTopic` answers for the four mock curriculum ids and nothing else. Every
 * real topic id comes from the backend as a curriculum CODE — `ALG-ORI-02` on
 * a `next_topic_handoff`, `ALG-KS3-01` on a fresh journey — so the lookup
 * missed on every live topic and both `/diagnostic/[topic]` and
 * `/orientation/[topic]` answered the miss with `notFound()`.
 *
 * There is no `not-found.tsx` under either route, so Next unmounted the
 * children inside AppFrame and left an empty div: a blank white page, produced
 * at the moment a student finishes one topic and is sent to the next.
 *
 * A missing curriculum entry is not a missing topic. The backend has the
 * content; the fixture simply does not list it. So this degrades instead —
 * the rule this codebase already follows for a field the backend stopped
 * sending.
 *
 * The title is taken from the session first because that is the only
 * authoritative name: `sessionTopicTitle` reads the orientation bundle, and
 * `phase4_review.topic_info` at Review. The curriculum title is the mock-mode
 * answer. The code itself is the last resort — deliberately printed raw rather
 * than prettied into "Alg Ori 02", because a name invented from a code is the
 * cause QA row 42 records.
 */

import { getTopic } from '@/lib/curriculum';

export interface DisplayTopic {
  id: string;
  title: string;
}

export function displayTopic(
  topicId: string,
  sessionTitle: string | null | undefined,
): DisplayTopic {
  const fromSession = sessionTitle?.trim();
  if (fromSession) return { id: topicId, title: fromSession };
  return { id: topicId, title: getTopic(topicId)?.title ?? topicId };
}
