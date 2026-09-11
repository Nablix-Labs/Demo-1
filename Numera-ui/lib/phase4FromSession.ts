/**
 * Reading the Phase 4 review off the ended session.
 *
 * The backend does not have an endpoint for this. Chiru's orchestration
 * (PR #156) generates the review once on entering Review and attaches it to
 * the session record as `phase4_review` — `app/models/session.py:294` — so
 * /session/end is where it arrives, and the client needs no second request.
 *
 * What arrives is `Phase4ReviewResponse`, Sanya's engine output. It once
 * carried only `tutor_replays` and `student_insights`; `topic_outcome`,
 * `question_journey`, `skill_labels`, and per-replay `question_text` and
 * `work_artifact` have all shipped since (verified against the VM 2026-09-11,
 * student ST015). The mappers below read every one of them — the list of
 * "not sent yet" fields that used to live here was stale, and stale in the
 * dangerous direction: it described fields the adapter was dropping as fields
 * the backend was not sending.
 *
 * Two things are still genuinely absent, and both degrade rather than guess:
 *
 *   topic_title    NOT on the wire at Review. The only human-readable name the
 *                  backend sends is the orientation video's title, and at
 *                  REVIEW `payload_type` is REVIEW_SUMMARY with a null
 *                  orientation_bundle — so `sessionTopicTitle` returns null and
 *                  the caller passes its own fallback. Resolving a name from
 *                  the topic CODE client-side is exactly what row 42 reported
 *                  (a review headed "Linear equations" for a session about
 *                  something else), so it is deliberately not done here.
 *                  Needs `topic_info.title` on Phase4ReviewResponse — Chiru.
 *   error_pattern  Never sent. `key_takeaways` likewise falls back to
 *                  `personalised_notes`. Both are optional by design.
 */

import type {
  Phase4Review, Phase4Replay, Phase4StudentInsights, Phase4ReplayStep,
  Phase4JourneyEntry, Phase4Evaluation,
} from '@/lib/api';

/** Sanya's engine output, as it sits on the session record. */
export interface SessionPhase4Review {
  tutor_replays?: Array<{
    review_item_id?: string;
    question_id?: string;
    attempt_id?: string;
    artifact_id?: string;
    first_error?: {
      summary?: string;
      /** Why the error is an error, as opposed to what it was. Its own card. */
      why_it_matters?: string | null;
      student_page_no?: number | null;
    };
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
  topic_outcome?: {
    mastery_status?: string;
    recommended_next_action?: string;
    /**
     * The encouraging sentence on the "Next action" card.
     *
     * Distinct from `recommended_next_action` beside it, which is a short chip
     * label ("Complete topic"). Authored per student by the engine, so there is
     * nothing to fall back to when it is absent — the card shows the label alone.
     */
    next_action_message?: string | null;
  } | null;
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
    /**
     * What the question TESTS, in two to four words.
     *
     * The backend merges this onto each journey row from its own `skill_labels`
     * list (session_service.py:1158-1200), so the client reads it here and
     * never has to join the two itself.
     */
    skill_label?: string | null;
  }>;
}

export interface SessionForPhase4 {
  student_id?: string;
  concept_id?: string;
  phase4_review?: SessionPhase4Review | null;
}

/** Shown when the backend sent no outcome. Deliberately not a mastery claim. */
export const OUTCOME_PENDING = 'Reviewed';

/**
 * `recommended_next_action` is the label on the button that ENDS the review, so
 * it has to read as something the student does.
 *
 * The backend currently supplies the Student Model's routing verb instead:
 * `build_phase4_review_request(..., event.routing.next_action)` at
 * session_service.py:1127. Those are WAIT_FOR_* tokens — WAIT_FOR_STUDENT_RESPONSE,
 * WAIT_FOR_CONTENT — addressed to the tutor loop, not the learner, and
 * `humanLabel` renders them verbatim: a 12-year-old finishing their topic was
 * asked to "Wait for student response" (verified live, ST015, 2026-09-11).
 *
 * Only that family is filtered, and it falls back to the same 'CONTINUE' used
 * when the field is absent entirely. Everything else is passed through
 * untouched — mapping unknown tokens onto invented wording is precisely how the
 * review came to be headed "Linear equations" for a session about something
 * else, and the backend owns this vocabulary.
 *
 * Remove once Chiru passes a genuine next action.
 */
function studentFacingAction(action: string | undefined): string {
  const token = action?.trim() ?? '';
  if (!token || token.toUpperCase().startsWith('WAIT_FOR')) return 'CONTINUE';
  return token;
}

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
      // Null rather than '' — FeedbackRail hides the card on a falsy value, and
      // an empty string would print a heading over nothing.
      why_it_matters: raw.first_error?.why_it_matters?.trim() || null,
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
 *
 * The KNOWN values are passed through unchanged, which PARTIAL made necessary.
 * This used to be `=== 'CORRECT' ? 'CORRECT' : 'WRONG'`, so a part-correct
 * answer was reported to the student as wrong — on a rail that carries a
 * three-state legend and a `statusOf` that already maps PARTIAL. The classifier
 * emits PARTIAL (ai_engine/classifier.py) and `QuestionJourneyItem.evaluation`
 * is a free string fed from the attempt, so it reaches the client intact.
 */
const KNOWN_EVALUATIONS = new Set<Phase4Evaluation>(
  ['CORRECT', 'PARTIAL', 'INCORRECT', 'WRONG'],
);

function evaluationOf(raw: string | undefined): Phase4Evaluation {
  const value = raw?.trim().toUpperCase() ?? '';
  return KNOWN_EVALUATIONS.has(value as Phase4Evaluation)
    ? (value as Phase4Evaluation)
    : 'WRONG';
}

function journeyFrom(
  raw: SessionPhase4Review['question_journey'],
  replays: Phase4Replay[],
): Phase4JourneyEntry[] {
  if (raw && raw.length > 0) {
    return raw.map((item, index) => ({
      question_id: item.question_id ?? '',
      question_text: item.question_text?.trim() || `Question ${index + 1}`,
      skill_label: item.skill_label?.trim() || null,
      evaluation: evaluationOf(item.evaluation),
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
      recommended_next_action: studentFacingAction(raw.topic_outcome?.recommended_next_action),
      next_action_message: raw.topic_outcome?.next_action_message?.trim() || null,
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
