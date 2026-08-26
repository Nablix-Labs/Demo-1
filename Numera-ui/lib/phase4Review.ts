/**
 * Phase 4 review — what the student is shown, and in what order.
 *
 * Two rules from the specification live here because both are easy to get
 * subtly wrong in JSX and impossible to test through it (the runner has no JSX
 * transform):
 *
 *   §3   A tutor replay follows a WRONG Phase 3 submission and nothing else.
 *        Not a hint, not a low score, not a question the student found hard —
 *        a correct answer reached after three hints is still correct, and
 *        replaying it would tell a student who got there that they did not.
 *
 *   §8.9 "Do not show backend IDs", and §9.3 lists question ids, attempt ids,
 *        micro-skill ids, error codes and misconception ids as internal. The
 *        journey rows below therefore carry a display label the screen can
 *        render and the ids stay on the payload, unread. The mockup circulated
 *        on 18 Aug shows `Q-T01-001` and `Micro-skill: T01.M5` on every card;
 *        that is the design the spec forbids, and the divergence is flagged to
 *        Sanya rather than silently resolved either way.
 */

import type { Phase4Replay, Phase4Review } from '@/lib/api';

export type JourneyStatus = 'correct' | 'incorrect';

export interface JourneyRow {
  /** "Question 3" — position in the Phase 3 journey, never the backend id. */
  label: string;
  questionText: string;
  status: JourneyStatus;
  /**
   * Index into `tutor_replays`, or null when this question has no replay.
   *
   * Null is the load-bearing case: §8.4 says a correct question "may show
   * completion status but do not launch a Tutor Replay", so the row must be
   * inert rather than merely unhighlighted.
   */
  replayIndex: number | null;
}

/**
 * The left rail: every Phase 3 question in the order it was served.
 *
 * A row is replayable only when the payload links it to a replay that actually
 * exists. Deriving it from `evaluation` instead would be a client-side
 * re-decision of §6.7's replay selection, which is Chiru's — and would put a
 * dead "play" affordance on any wrong answer he chose not to replay.
 */
export function journeyRows(review: Phase4Review): JourneyRow[] {
  const replayIndexById = new Map<string, number>();
  review.tutor_replays.forEach((r, i) => replayIndexById.set(r.review_item_id, i));

  return review.question_journey.map((entry, i) => ({
    label: `Question ${i + 1}`,
    questionText: entry.question_text,
    status: entry.evaluation === 'CORRECT' ? 'correct' : 'incorrect',
    replayIndex: entry.review_item_id != null
      ? replayIndexById.get(entry.review_item_id) ?? null
      : null,
  }));
}

/**
 * "Review 1 of 2" (§8.8) — counted over the REPLAYS, not the journey.
 *
 * The mockup reads "Reviewing Question 3 of 8" over all eight questions, which
 * tells a student who got six right that they have six more corrections to sit
 * through. Null when there is nothing to replay, so the caller renders no
 * progress line rather than "Review 0 of 0".
 */
export function reviewProgressLabel(index: number, total: number): string | null {
  // One check, not two: `index >= total` already covers the empty list, since
  // any index into nothing is out of range.
  if (index < 0 || index >= total) return null;
  return `Review ${index + 1} of ${total}`;
}

/**
 * §8.8: with no wrong answers the replay section is skipped entirely and the
 * student goes straight to the Learning Summary. An empty replay list is the
 * expected shape of a topic answered correctly — never an error.
 */
export function skipsReplay(review: Phase4Review): boolean {
  return review.tutor_replays.length === 0;
}

/** The replay at `index`, or null when the index is outside the list. */
export function replayAt(review: Phase4Review, index: number): Phase4Replay | null {
  return review.tutor_replays[index] ?? null;
}

/**
 * Which page of the student's work to open on.
 *
 * §7.5 lets `first_error.student_page_no` locate the mistake, so a multi-page
 * submission opens on the page the error is on instead of making the student
 * hunt for it. Out-of-range values fall back to page 1: the page number comes
 * from the model's reading of the work, and a replay is not worth discarding
 * because it counted pages wrong.
 */
export function openingPageNo(replay: Phase4Replay): number {
  const wanted = replay.first_error.student_page_no;
  if (typeof wanted !== 'number') return 1;
  if (wanted < 1 || wanted > replay.work_artifact.page_count) return 1;
  return wanted;
}
