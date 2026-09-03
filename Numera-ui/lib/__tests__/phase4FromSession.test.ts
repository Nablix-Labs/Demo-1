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

/**
 * The backend's own topic outcome, not the client's placeholder.
 *
 * Verified live on 29 Aug against the deployed build: a payload carrying
 * `topic_outcome: { mastery_status: 'DEVELOPING' }` rendered as
 * "TOPIC OUTCOME · REVIEWED · Next: continue". The placeholder was written for
 * a backend that sent nothing, and then went on overwriting one that does.
 */
describe('topic outcome', () => {
  const base = {
    student_id: 'ST015',
    concept_id: 'T01',
    phase4_review: {
      tutor_replays: [],
      student_insights: {
        strength_summary: 'Secure on the arithmetic.',
        next_practice_focus: 'Writing a rule with a letter.',
      },
    },
  };

  it('renders what the backend actually sent', () => {
    const r = phase4FromSession({
      ...base,
      phase4_review: {
        ...base.phase4_review,
        topic_outcome: { mastery_status: 'DEVELOPING', recommended_next_action: 'REPAIR' },
      },
    } as never, 'Algebra');
    expect(r!.topic_outcome.mastery_status).toBe('DEVELOPING');
    expect(r!.topic_outcome.recommended_next_action).toBe('REPAIR');
  });

  it('falls back only when the backend sent none — and never claims mastery', () => {
    const r = phase4FromSession(base as never, 'Algebra');
    expect(r!.topic_outcome.mastery_status).toBe(OUTCOME_PENDING);
    expect(OUTCOME_PENDING).not.toMatch(/master/i);
  });

  it('ignores an empty string rather than printing a blank outcome', () => {
    const r = phase4FromSession({
      ...base,
      phase4_review: { ...base.phase4_review, topic_outcome: { mastery_status: '   ' } },
    } as never, 'Algebra');
    expect(r!.topic_outcome.mastery_status).toBe(OUTCOME_PENDING);
  });
});

describe('the journey rail lists the whole Phase 3 journey', () => {
  const insights = { strength_summary: 'ok', next_practice_focus: 'ok' };

  const replay = (n: number) => ({
    review_item_id: `RI-${n}`,
    question_id: `Q-${n}`,
    attempt_id: `A-${n}`,
    artifact_id: `ART-${n}`,
    question_text: `Question ${n} text`,
    replay_steps: [{ sequence_no: 1, tutor_write: 'x', narration: 'y' }],
  });

  it('uses the backend journey when it is sent, including correct answers', () => {
    // The rail derived itself from `tutor_replays`, which are the WRONG
    // attempts only — so a student who answered everything correctly saw an
    // empty column instead of the questions they got right.
    const review = phase4FromSession({
      phase4_review: {
        tutor_replays: [],
        student_insights: insights,
        question_journey: [
          { question_id: 'Q-1', question_text: 'First', evaluation: 'CORRECT', review_item_id: null },
          { question_id: 'Q-2', question_text: 'Second', evaluation: 'CORRECT', review_item_id: null },
        ],
      },
    } as never, 'Topic')!;
    expect(review.question_journey).toHaveLength(2);
    expect(review.question_journey.map((e) => e.evaluation)).toEqual(['CORRECT', 'CORRECT']);
    expect(review.question_journey[0].question_text).toBe('First');
  });

  it('keeps the explicit replay link rather than matching on question_id', () => {
    const review = phase4FromSession({
      phase4_review: {
        tutor_replays: [replay(2)],
        student_insights: insights,
        question_journey: [
          { question_id: 'Q-1', question_text: 'First', evaluation: 'CORRECT', review_item_id: null },
          { question_id: 'Q-2', question_text: 'Second', evaluation: 'WRONG', review_item_id: 'RI-2' },
        ],
      },
    } as never, 'Topic')!;
    expect(review.question_journey[0].review_item_id).toBeNull();
    expect(review.question_journey[1].review_item_id).toBe('RI-2');
  });

  it('never defaults evaluation to CORRECT', () => {
    // The backend always sends it; a default would mislabel a wrong answer as
    // right on the one screen that reports how the student did.
    const review = phase4FromSession({
      phase4_review: {
        tutor_replays: [],
        student_insights: insights,
        question_journey: [
          { question_id: 'Q-1', question_text: 'First', evaluation: 'WRONG', review_item_id: null },
        ],
      },
    } as never, 'Topic')!;
    expect(review.question_journey[0].evaluation).toBe('WRONG');
  });

  it('falls back to the replays when the backend sends no journey', () => {
    const review = phase4FromSession({
      phase4_review: { tutor_replays: [replay(1)], student_insights: insights },
    } as never, 'Topic')!;
    expect(review.question_journey).toHaveLength(1);
    expect(review.question_journey[0].review_item_id).toBe('RI-1');
    expect(review.question_journey[0].evaluation).toBe('WRONG');
  });
});
