/**
 * Reading the Phase 4 review off the ended session.
 *
 * The backend does not have an endpoint for this. Chiru's orchestration
 * (PR #156) generates the review once on entering Review and attaches it to
 * the session record as `phase4_review` — `app/models/session.py:294` — so
 * /session/end is where it arrives, and the client needs no second request.
 *
 * What arrives is `Phase4ReviewResponse`, which is exactly Sanya's engine
 * output: `tutor_replays` and `student_insights`, nothing else. The screen
 * needs four things that are not in it, so this adapter fills what it can from
 * the session record and degrades honestly on the rest:
 *
 *   topic_title          taken from the session record.
 *   topic_outcome        NOT sent. Shown as "in review" rather than guessed —
 *                        §6.9 makes mastery authoritative backend data, and a
 *                        client-side guess at it is a second source of truth
 *                        for the one thing the spec says has one.
 *   question_journey     NOT sent. Falls back to the replayed questions alone,
 *                        so the rail lists the corrections rather than the
 *                        whole Phase 3 journey. The questions answered
 *                        correctly are simply absent — visibly incomplete, not
 *                        silently wrong.
 *   question_text        NOT on TutorReplay (it is on Chiru's ReplayItem and
 *                        dropped from her output). Falls back to the position.
 *   work_artifact        NOT on TutorReplay either — it carries `artifact_id`
 *                        alone, with no `pdf_url` or `page_count`, so the work
 *                        panel shows its unavailable state until he merges
 *                        those through.
 *
 * Every one of those is a field to be added in his merge step (§6.10 step 2),
 * not a thing to compute here.
 */

import type {
  Phase4Review, Phase4Replay, Phase4StudentInsights, Phase4ReplayStep,
  Phase4JourneyEntry,
} from '@/lib/api';

/** Sanya's engine output, as it sits on the session record. */
export interface SessionPhase4Review {
  tutor_replays?: Array<{
    review_item_id?: string;
    question_id?: string;
    attempt_id?: string;
    artifact_id?: string;
    first_error?: { summary?: string; student_page_no?: number | null };
    replay_steps?: Phase4ReplayStep[];
    // Present only once Chiru merges them through — see the header.
    question_text?: string;
    work_artifact?: { artifact_id?: string; pdf_url?: string; page_count?: number };
  }>;
  student_insights?: Partial<Phase4StudentInsights>;
  /**
   * The real outcome, forwarded by the backend after generation.
   *
   * Optional on the wire (`TopicOutcome | None`, phase4_review.py:177) and so
   * optional here, but when it IS sent it is the authority — see below for what
   * reading it fixes.
   */
  topic_outcome?: { mastery_status?: string; recommended_next_action?: string } | null;
  /**
   * The whole Phase 3 journey, correct answers included.
   *
   * `question_text` is required and non-empty on the backend model
   * (`QuestionJourneyItem`, phase4_review.py:171) and `review_item_id` is the
   * explicit link to a replay, null when the attempt has none.
   */
  question_journey?: Array<{
    question_id?: string;
    question_text?: string;
    evaluation?: string;
    review_item_id?: string | null;
  }>;
}

export interface SessionForPhase4 {
  student_id?: string;
  concept_id?: string;
  phase4_review?: SessionPhase4Review | null;
}

/** Shown when the backend sent no outcome. Deliberately not a mastery claim. */
export const OUTCOME_PENDING = 'Reviewed';

function toReplay(
  raw: NonNullable<SessionPhase4Review['tutor_replays']>[number],
  index: number,
): Phase4Replay | null {
  const reviewItemId = raw.review_item_id?.trim();
  const steps = raw.replay_steps ?? [];
  // A replay with no id cannot be selected from the rail, and one with no steps
  // would put an empty board on the largest area of the screen. Neither is
  // worth rendering; dropping it leaves the rest of the review usable.
  if (!reviewItemId || steps.length === 0) return null;

  return {
    review_item_id: reviewItemId,
    question_id: raw.question_id ?? '',
    attempt_id: raw.attempt_id ?? '',
    artifact_id: raw.artifact_id ?? '',
    question_text: raw.question_text?.trim() || `Question ${index + 1}`,
    first_error: {
      summary: raw.first_error?.summary ?? '',
      student_page_no: raw.first_error?.student_page_no ?? null,
    },
    replay_steps: steps,
    work_artifact: {
      artifact_id: raw.work_artifact?.artifact_id ?? raw.artifact_id ?? '',
      // Zero pages, so the selector stays hidden rather than offering a page
      // that cannot be opened.
      page_count: raw.work_artifact?.page_count ?? 0,
      pdf_url: raw.work_artifact?.pdf_url ?? '',
    },
  };
}

/**
 * The journey rows: the backend's own list when it sent one, the replays when
 * it did not.
 *
 * `evaluation` is never defaulted. The backend always sends it, and a default
 * of CORRECT would mislabel a wrong answer as right on the one screen that
 * reports how the student did — so an unrecognised value is carried through as
 * WRONG, which is the reading that cannot flatter.
 */
function journeyFrom(
  raw: SessionPhase4Review['question_journey'],
  replays: Phase4Replay[],
): Phase4JourneyEntry[] {
  if (raw && raw.length > 0) {
    return raw.map((item, index) => ({
      question_id: item.question_id ?? '',
      question_text: item.question_text?.trim() || `Question ${index + 1}`,
      evaluation: item.evaluation?.trim().toUpperCase() === 'CORRECT' ? 'CORRECT' : 'WRONG',
      review_item_id: item.review_item_id ?? null,
    }));
  }
  return replays.map((replay) => ({
    question_id: replay.question_id,
    question_text: replay.question_text,
    evaluation: 'WRONG' as const,
    review_item_id: replay.review_item_id,
  }));
}

/**
 * Returns null when the session carries no review, which is the ordinary case
 * for a topic that has not reached Review — never an error.
 */
export function phase4FromSession(
  session: SessionForPhase4 | null | undefined,
  topicTitle: string,
): Phase4Review | null {
  const raw = session?.phase4_review;
  const insights = raw?.student_insights;
  // Both halves are required: the summary is the part every student sees,
  // including the one who got everything right (§8.8), so a payload with
  // replays but no insights has nothing to end on.
  if (!raw || !insights?.strength_summary || !insights?.next_practice_focus) return null;

  const tutor_replays = (raw.tutor_replays ?? [])
    .map(toReplay)
    .filter((r): r is Phase4Replay => r !== null);

  return {
    student_id: session?.student_id ?? '',
    topic_id: session?.concept_id ?? '',
    topic_title: topicTitle,
    // The backend's own outcome wins.
    //
    // This was hardcoded to OUTCOME_PENDING / 'CONTINUE' unconditionally, so a
    // reply carrying `topic_outcome: { mastery_status: 'DEVELOPING' }` was
    // rendered as "REVIEWED · Next: continue". Verified live on 29 Aug against
    // the deployed build: the payload said DEVELOPING and the screen said
    // REVIEWED. The placeholder was written for a backend that sent nothing and
    // then kept overwriting one that does.
    //
    // The fallback stays for the case it was built for — both fields are
    // genuinely optional on the wire — and it is deliberately not a mastery
    // claim, which is the whole reason OUTCOME_PENDING reads "Reviewed".
    topic_outcome: {
      mastery_status: raw.topic_outcome?.mastery_status?.trim() || OUTCOME_PENDING,
      recommended_next_action: raw.topic_outcome?.recommended_next_action?.trim() || 'CONTINUE',
    },
    // Taken from the backend, which sends the whole Phase 3 journey.
    //
    // This used to be derived from `tutor_replays`, because the two fields a
    // journey row needs were missing from `QuestionJourneyItem`. Both have
    // since shipped: `question_text` is required and non-empty
    // (phase4_review.py:171), and `review_item_id` is an explicit link, null
    // when an attempt has no replay. So the reason for deriving is gone.
    //
    // It mattered because the replays are the WRONG attempts only. A student
    // who answered everything correctly produced no replays, so the rail
    // rendered empty on exactly the run that went best.
    //
    // The link stays explicit rather than matched on `question_id`: one
    // question can be answered wrong, repaired in Phase 2 and answered again,
    // so an id identifies a question and not an attempt, and matching on it
    // would attach a single replay to two rows.
    //
    // The replay-derived shape is kept as the fallback for a backend that
    // sends no journey — listing the corrections is incomplete, but it is not
    // wrong, and it is what this screen showed before.
    question_journey: journeyFrom(raw?.question_journey, tutor_replays),
    tutor_replays,
    student_insights: {
      strength_summary: insights.strength_summary,
      development_summary: insights.development_summary ?? '',
      learning_pattern_summary: insights.learning_pattern_summary ?? null,
      recent_improvement_summary: insights.recent_improvement_summary ?? null,
      next_practice_focus: insights.next_practice_focus,
      personalised_notes: insights.personalised_notes ?? [],
    },
  };
}
