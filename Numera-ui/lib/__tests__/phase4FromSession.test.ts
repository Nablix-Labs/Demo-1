/**
 * Reading the Phase 4 review off the ended session.
 *
 * The backend attaches Sanya's engine output to the session record and nothing
 * more (app/models/session.py:294). Most of these tests are about what happens
 * to the fields it does NOT send — the screen has to be visibly incomplete
 * rather than quietly wrong, because the alternative is a client-side guess at
 * mastery, which §6.9 makes the backend's alone.
 */

import { describe, expect, it } from 'vitest';
import { phase4FromSession, OUTCOME_PENDING, type SessionForPhase4 } from '@/lib/phase4FromSession';

const INSIGHTS = {
  strength_summary: 'You kept the fixed operation in place.',
  development_summary: 'Choosing the operation from the words.',
  next_practice_focus: 'Decide whether the quantity increases or decreases.',
  personalised_notes: ['one', 'two', 'three'],
};

const REPLAY = {
  review_item_id: 'REV-1',
  question_id: 'Q-T01-005',
  attempt_id: 'ATTEMPT-021',
  artifact_id: 'ART-1',
  first_error: { summary: 'Treated "falls" as addition.', student_page_no: 2 },
  replay_steps: [{ sequence_no: 1, narration: 'Start with t.', tutor_write: 'Start: t' }],
};

const session = (over: Partial<SessionForPhase4> = {}): SessionForPhase4 => ({
  student_id: 'ST003',
  concept_id: 'ALG-KS3-01',
  phase4_review: { tutor_replays: [REPLAY], student_insights: INSIGHTS },
  ...over,
});

describe('a session that carries no review', () => {
  it('is not an error', () => {
    // The ordinary case for a topic that has not reached Review.
    expect(phase4FromSession(session({ phase4_review: null }), 'Algebra')).toBeNull();
    expect(phase4FromSession(null, 'Algebra')).toBeNull();
  });

  it('is refused when generation produced no insights', () => {
    // Every student sees the summary, including one who got everything right
    // (§8.8), so replays without insights have nothing to end on.
    expect(phase4FromSession(
      session({ phase4_review: { tutor_replays: [REPLAY], student_insights: {} } }),
      'Algebra',
    )).toBeNull();
  });
});

describe('what the backend does send', () => {
  it('carries the replay and its steps through intact', () => {
    const review = phase4FromSession(session(), 'What Is Algebra?');
    expect(review?.tutor_replays).toHaveLength(1);
    expect(review?.tutor_replays[0].replay_steps[0].tutor_write).toBe('Start: t');
    expect(review?.tutor_replays[0].first_error.student_page_no).toBe(2);
    expect(review?.topic_title).toBe('What Is Algebra?');
  });

  it('keeps a null insight null rather than defaulting it to a string', () => {
    // §8.9 hides the section on null. Defaulting to '' would also hide it, but
    // defaulting to anything else would assert a pattern the engine declined to.
    const review = phase4FromSession(session(), 'Algebra');
    expect(review?.student_insights.learning_pattern_summary).toBeNull();
    expect(review?.student_insights.recent_improvement_summary).toBeNull();
  });
});

describe('what the backend does not send yet', () => {
  it('does not invent a mastery status', () => {
    // §6.9 makes mastery authoritative backend data. Guessing "MASTERED" here
    // would tell a student they had finished a topic on no evidence at all.
    const review = phase4FromSession(session(), 'Algebra');
    expect(review?.topic_outcome.mastery_status).toBe(OUTCOME_PENDING);
    expect(review?.topic_outcome.mastery_status).not.toMatch(/MASTER/i);
  });

  it('falls back to the replayed questions for the rail', () => {
    // The full Phase 3 journey is not sent, so the correct questions are simply
    // absent. Incomplete and visibly so, rather than a rail that claims the
    // student got nothing right.
    const review = phase4FromSession(session(), 'Algebra');
    expect(review?.question_journey).toHaveLength(1);
    expect(review?.question_journey[0].review_item_id).toBe('REV-1');
  });

  it('hides the page selector when no page count was sent', () => {
    // A selector over pages that cannot be opened is a control that does nothing.
    const review = phase4FromSession(session(), 'Algebra');
    expect(review?.tutor_replays[0].work_artifact.page_count).toBe(0);
    expect(review?.tutor_replays[0].work_artifact.pdf_url).toBe('');
  });

  it('labels a replay by position when no question text was merged in', () => {
    const review = phase4FromSession(session(), 'Algebra');
    expect(review?.tutor_replays[0].question_text).toBe('Question 1');
  });

  it('prefers the merged fields once Chiru sends them', () => {
    const review = phase4FromSession(session({
      phase4_review: {
        tutor_replays: [{
          ...REPLAY,
          question_text: 'A temperature t falls by 3.',
          work_artifact: { artifact_id: 'ART-1', pdf_url: '/work.pdf', page_count: 3 },
        }],
        student_insights: INSIGHTS,
      },
    }), 'Algebra');
    expect(review?.tutor_replays[0].question_text).toBe('A temperature t falls by 3.');
    expect(review?.tutor_replays[0].work_artifact).toMatchObject({ pdf_url: '/work.pdf', page_count: 3 });
  });
});

describe('a malformed replay', () => {
  it('is dropped rather than rendering an empty board', () => {
    // The board is the largest area on the screen; a replay with no steps would
    // put nothing on it. Dropping one leaves the rest of the review usable.
    const review = phase4FromSession(session({
      phase4_review: {
        tutor_replays: [REPLAY, { ...REPLAY, review_item_id: 'REV-2', replay_steps: [] }],
        student_insights: INSIGHTS,
      },
    }), 'Algebra');
    expect(review?.tutor_replays.map((r) => r.review_item_id)).toEqual(['REV-1']);
  });
});
