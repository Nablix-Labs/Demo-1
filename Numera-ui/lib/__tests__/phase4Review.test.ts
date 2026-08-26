/**
 * What Phase 4 replays, and what it refuses to replay.
 *
 * §3 is one rule — wrong submission replays, correct submission does not — and
 * every test here is a way of getting it wrong that the specification calls out
 * by name: replaying because a hint was used, replaying the corrected answer
 * instead of the mistake, losing the original wrong question once a fresh one
 * was served.
 */

import { describe, expect, it } from 'vitest';
import {
  journeyRows, reviewProgressLabel, skipsReplay, replayAt, openingPageNo,
} from '@/lib/phase4Review';
import type { Phase4Replay, Phase4Review, Phase4JourneyEntry } from '@/lib/api';

function replay(id: string, over: Partial<Phase4Replay> = {}): Phase4Replay {
  return {
    review_item_id: id,
    question_id: `Q-${id}`,
    attempt_id: `ATTEMPT-${id}`,
    artifact_id: `ART-${id}`,
    question_text: 'Find a rule for each set.',
    first_error: { summary: 'Treated "falls by 3" as addition.', student_page_no: null },
    replay_steps: [{ sequence_no: 1, narration: 'Start with t.', tutor_write: 'Start: t' }],
    work_artifact: { artifact_id: `ART-${id}`, page_count: 1, pdf_url: '/work.pdf' },
    ...over,
  };
}

function entry(
  evaluation: Phase4JourneyEntry['evaluation'],
  reviewItemId: string | null,
  text = 'A question',
): Phase4JourneyEntry {
  return { question_id: `Q-${text}`, question_text: text, evaluation, review_item_id: reviewItemId };
}

function review(over: Partial<Phase4Review> = {}): Phase4Review {
  return {
    student_id: 'ST003',
    topic_id: 'ALG-KS3-01',
    topic_title: 'What Is Algebra?',
    topic_outcome: { mastery_status: 'MASTERED', recommended_next_action: 'START_NEXT_TOPIC' },
    question_journey: [],
    tutor_replays: [],
    student_insights: {
      strength_summary: 's', development_summary: 'd',
      learning_pattern_summary: null, recent_improvement_summary: null,
      next_practice_focus: 'n', personalised_notes: ['a', 'b', 'c'],
    },
    ...over,
  };
}

describe('the question journey rail', () => {
  it('numbers questions by position and never shows the backend id', () => {
    const rows = journeyRows(review({
      question_journey: [entry('CORRECT', null, 'first'), entry('WRONG', 'REV-1', 'second')],
      tutor_replays: [replay('REV-1')],
    }));

    expect(rows.map((r) => r.label)).toEqual(['Question 1', 'Question 2']);
    // §8.9 "Do not show backend IDs" — the mockup puts Q-T01-001 on every card.
    expect(JSON.stringify(rows)).not.toContain('Q-');
  });

  it('makes a correct question inert, not merely unhighlighted', () => {
    // §8.4: correct questions "may show completion status but do not launch a
    // Tutor Replay". A null index is what stops the row being clickable at all.
    const rows = journeyRows(review({
      question_journey: [entry('CORRECT', null)],
      tutor_replays: [],
    }));
    expect(rows[0]).toMatchObject({ status: 'correct', replayIndex: null });
  });

  it('does not replay a correct answer that needed a hint', () => {
    // §3 Case D, and §6.11: "Correct questions never enter replay merely because
    // hints were used." Hint usage is evidence; it is not a mistake.
    const rows = journeyRows(review({
      question_journey: [entry('CORRECT', null, 'answered after a hint')],
      tutor_replays: [],
    }));
    expect(rows[0].replayIndex).toBeNull();
  });

  it('keeps the original wrong question once a fresh one was served', () => {
    // §3 Case B / §6.11: the initial wrong Q1 stays reviewable even though the
    // student went on to answer the fresh Q2 correctly. Dropping it is how a
    // student ends a topic never seeing the mistake explained.
    const rows = journeyRows(review({
      question_journey: [entry('WRONG', 'REV-1', 'initial'), entry('CORRECT', null, 'fresh')],
      tutor_replays: [replay('REV-1')],
    }));
    expect(rows[0].replayIndex).toBe(0);
    expect(rows[1].replayIndex).toBeNull();
  });

  it('replays both wrong attempts but not the correct one after repair', () => {
    // §3 Case C: wrong Q1, wrong fresh Q2, Phase 2 repair, then Q2 correct.
    // "Do not replay final correct Q."
    const rows = journeyRows(review({
      question_journey: [
        entry('WRONG', 'REV-1', 'initial'),
        entry('WRONG', 'REV-2', 'fresh'),
        entry('CORRECT', null, 'fresh again after repair'),
      ],
      tutor_replays: [replay('REV-1'), replay('REV-2')],
    }));
    expect(rows.map((r) => r.replayIndex)).toEqual([0, 1, null]);
  });

  it('leaves a wrong question inert when the backend sent no replay for it', () => {
    // Replay selection is Chiru's (§6.7). A row that offers a replay the payload
    // does not contain is a control that does nothing when pressed.
    const rows = journeyRows(review({
      question_journey: [entry('WRONG', 'REV-MISSING')],
      tutor_replays: [],
    }));
    expect(rows[0].replayIndex).toBeNull();
  });

  it('attaches each replay to its own row when one question was attempted twice', () => {
    // The same question_id appears twice (wrong, then wrong again). Matching on
    // question_id rather than review_item_id would give both rows replay 0.
    const shared = 'Q-T01-005';
    const rows = journeyRows(review({
      question_journey: [
        { question_id: shared, question_text: 'q', evaluation: 'WRONG', review_item_id: 'REV-1' },
        { question_id: shared, question_text: 'q', evaluation: 'WRONG', review_item_id: 'REV-2' },
      ],
      tutor_replays: [replay('REV-1'), replay('REV-2')],
    }));
    expect(rows.map((r) => r.replayIndex)).toEqual([0, 1]);
  });
});

describe('review progress', () => {
  it('counts over the replays, not the whole journey', () => {
    // §8.8's example is "Review 1 of 2". The mockup's "Question 3 of 8" tells a
    // student who got six right that six corrections are still coming.
    expect(reviewProgressLabel(0, 2)).toBe('Review 1 of 2');
    expect(reviewProgressLabel(1, 2)).toBe('Review 2 of 2');
  });

  it('says nothing when there is nothing to replay', () => {
    expect(reviewProgressLabel(0, 0)).toBeNull();
  });

  it('says nothing once the last replay is past', () => {
    expect(reviewProgressLabel(2, 2)).toBeNull();
    expect(reviewProgressLabel(-1, 2)).toBeNull();
  });
});

describe('a topic with no wrong answers', () => {
  it('skips the replay section entirely', () => {
    // §8.8. An empty replay list is a student who got everything right, not a
    // payload that failed to load.
    expect(skipsReplay(review({ tutor_replays: [] }))).toBe(true);
  });

  it('does not skip when a replay exists', () => {
    expect(skipsReplay(review({ tutor_replays: [replay('REV-1')] }))).toBe(false);
  });
});

describe('reading a replay by index', () => {
  it('returns null past the end rather than undefined', () => {
    const r = review({ tutor_replays: [replay('REV-1')] });
    expect(replayAt(r, 0)?.review_item_id).toBe('REV-1');
    expect(replayAt(r, 1)).toBeNull();
    expect(replayAt(r, -1)).toBeNull();
  });
});

describe('which page of the work to open on', () => {
  const threePages = { artifact_id: 'ART-1', page_count: 3, pdf_url: '/work.pdf' };

  it('opens on the page the first error is on', () => {
    expect(openingPageNo(replay('REV-1', {
      work_artifact: threePages,
      first_error: { summary: 'x', student_page_no: 2 },
    }))).toBe(2);
  });

  it('opens on page 1 when the error is not page-located', () => {
    expect(openingPageNo(replay('REV-1', {
      work_artifact: threePages,
      first_error: { summary: 'x', student_page_no: null },
    }))).toBe(1);
  });

  it('opens on page 1 rather than a page that does not exist', () => {
    // The page number is the model's reading of the work. A replay is not worth
    // discarding, or a blank frame worth showing, because it miscounted.
    expect(openingPageNo(replay('REV-1', {
      work_artifact: threePages,
      first_error: { summary: 'x', student_page_no: 9 },
    }))).toBe(1);
    expect(openingPageNo(replay('REV-1', {
      work_artifact: threePages,
      first_error: { summary: 'x', student_page_no: 0 },
    }))).toBe(1);
  });
});
