/**
 * Phase 4 against the REAL backend payload.
 *
 * The other Phase 4 tests use fixtures I wrote. This one uses the response the
 * backend actually produces — `Phase4ReviewResponse` from
 * `app/models/phase4_review.py`, which is exactly:
 *
 *     { tutor_replays: TutorReplay[], student_insights: StudentInsights }
 *
 * and where `TutorReplay` is exactly:
 *
 *     review_item_id, question_id, attempt_id, artifact_id,
 *     first_error, replay_steps
 *
 * — no `question_text`, no `work_artifact`. Written before the integration has
 * ever succeeded (student_model 403s on /topic/event-history), so that when it
 * is unblocked we find out here rather than on a student's screen.
 */

import { describe, expect, it } from 'vitest';
import { phase4FromSession, OUTCOME_PENDING } from '@/lib/phase4FromSession';
import { journeyRows, skipsReplay, replayAt, openingPageNo, reviewProgressLabel } from '@/lib/phase4Review';
import { insightSections, keyTakeaways } from '@/lib/phase4Insights';
import { boardDraw } from '@/lib/phase4Board';

/** Exactly what StudentInsights requires: 3-5 notes, two nullable summaries. */
const INSIGHTS = {
  strength_summary: 'You identified the changing quantity across several questions.',
  development_summary: 'Choosing the operation from the words in the question.',
  learning_pattern_summary: null,
  recent_improvement_summary: null,
  next_practice_focus: 'Decide whether the quantity increases or decreases first.',
  personalised_notes: ['Note one.', 'Note two.', 'Note three.'],
};

/** Exactly what TutorReplay carries — nothing more. */
const REPLAY = {
  review_item_id: 'REV-001',
  question_id: 'Q-T01-002',
  attempt_id: 'ATTEMPT-018',
  artifact_id: 'ART-000122',
  first_error: { summary: 'The first error was treating the 5 as a multiplier.', student_page_no: 1 },
  replay_steps: [
    { sequence_no: 1, narration: 'Look at what changes.', tutor_write: 'What changes?' },
    { sequence_no: 2, narration: 'The five never changes.', tutor_write: '+ 5 stays' },
    { sequence_no: 3, narration: 'So the rule is n plus five.', tutor_write: 'n + 5' },
  ],
};

const session = (review: unknown) => ({
  student_id: 'ST019',
  concept_id: 'ALG-KS3-01',
  phase4_review: review,
}) as never;

describe('a topic with one wrong answer', () => {
  const review = phase4FromSession(
    session({ tutor_replays: [REPLAY], student_insights: INSIGHTS }),
    'What Is Algebra?',
  );

  it('renders at all — the screen appears instead of the legacy worksheets', () => {
    expect(review).not.toBeNull();
  });

  it('keeps the replay, so the tutor board actually plays', () => {
    // replay_steps is the one rich thing the response does carry.
    expect(review!.tutor_replays).toHaveLength(1);
    expect(skipsReplay(review!)).toBe(false);
    expect(replayAt(review!, 0)!.replay_steps).toHaveLength(3);
  });

  it('drives the board from the steps without inventing geometry', () => {
    const draw = boardDraw(-1, 0, replayAt(review!, 0)!.replay_steps);
    expect(draw.elements.length).toBeGreaterThan(0);
  });

  it('labels the rail without leaking backend ids (§9.3)', () => {
    const rows = journeyRows(review!);
    expect(rows[0].label).toBe('Question 1');
    expect(JSON.stringify(rows)).not.toContain('ATTEMPT-018');
    expect(rows[0].replayIndex).toBe(0);
  });

  it('counts progress over the replays, not the whole journey', () => {
    expect(reviewProgressLabel(0, review!.tutor_replays.length)).toBe('Review 1 of 1');
  });

  it('degrades the work panel instead of breaking, since pdf_url is not sent', () => {
    // TutorReplay carries artifact_id alone. page_count 0 keeps the page
    // selector hidden rather than offering a page that cannot open.
    const artifact = replayAt(review!, 0)!.work_artifact;
    expect(artifact.artifact_id).toBe('ART-000122');
    expect(artifact.pdf_url).toBe('');
    expect(artifact.page_count).toBe(0);
    // openingPageNo must not return the backend's page 1 against a 0-page doc.
    expect(openingPageNo(replayAt(review!, 0)!)).toBe(1);
  });

  it('falls back to a position when question_text is not sent', () => {
    expect(replayAt(review!, 0)!.question_text).toBe('Question 1');
  });

  it('shows no mastery claim, because topic_outcome is not sent', () => {
    expect(review!.topic_outcome.mastery_status).toBe(OUTCOME_PENDING);
  });

  it('hides the two nullable insight sections rather than printing empty headings', () => {
    const keys = insightSections(review!.student_insights).map((s) => s.key);
    expect(keys).toContain('strength');
    expect(keys).not.toContain('pattern');
    expect(keys).not.toContain('improvement');
  });

  it('falls back to personalised_notes for the takeaways', () => {
    expect(keyTakeaways(review!)).toHaveLength(3);
  });
});

describe('a perfect run — the case Manjusha actually tested', () => {
  // filter_replay_attempts returns wrong Phase 3 attempts only, so 6/6 correct
  // produces an EMPTY replay list. This must render the summary, not look broken.
  const review = phase4FromSession(
    session({ tutor_replays: [], student_insights: INSIGHTS }),
    'What Is Algebra?',
  );

  it('still shows the review screen', () => {
    expect(review).not.toBeNull();
  });

  it('skips the replay section entirely (§8.8)', () => {
    expect(skipsReplay(review!)).toBe(true);
    expect(journeyRows(review!)).toEqual([]);
    expect(reviewProgressLabel(0, 0)).toBeNull();
  });

  it('still gives the student their summary — the part everyone gets', () => {
    expect(insightSections(review!.student_insights).length).toBeGreaterThan(0);
    expect(keyTakeaways(review!)).toHaveLength(3);
  });
});

describe('what must NOT render the Phase 4 screen', () => {
  it('no review on the session — the ordinary pre-Review case', () => {
    expect(phase4FromSession(session(null), 'T')).toBeNull();
    expect(phase4FromSession(session(undefined), 'T')).toBeNull();
  });

  it('a review that failed to generate, which is what the 403 produces today', () => {
    // generate_phase4_review_for degrades to None on failure, so this is the
    // shape currently arriving in production.
    expect(phase4FromSession(session(null), 'T')).toBeNull();
  });

  it('replays with no steps are dropped rather than shown as a blank board', () => {
    const review = phase4FromSession(
      session({
        tutor_replays: [{ ...REPLAY, replay_steps: [] }],
        student_insights: INSIGHTS,
      }),
      'T',
    );
    expect(review!.tutor_replays).toEqual([]);
  });
});
