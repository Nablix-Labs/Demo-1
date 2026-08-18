/**
 * A worked Phase 4 payload, for /dev-screens/phase4.
 *
 * This exists because the backend half does not: §6.10's "Send the review
 * response to Manav" has no shape in the specification and Chiru's
 * orchestration is unwritten, so without a fixture the screen cannot be looked
 * at by anyone until his work lands.
 *
 * It is reachable ONLY from the dev route. It is deliberately not wired into
 * /review as a fallback: a review screen that shows invented results when the
 * real ones fail to load presents fake work as the student's own, which is the
 * exact failure the existing review page already carries an empty state for
 * (see the endFailed branch in app/review/page.tsx).
 *
 * The content follows §11 Scenario 3 — wrong, fresh wrong, Phase 2 repair, then
 * correct — because it is the scenario with the most ways to get the replay
 * selection wrong: two replays, and a final correct attempt that must NOT be
 * replayed but must still feed the improvement summary.
 */

import type { Phase4Review } from '@/lib/api';

const PAGE = 'data:image/svg+xml;utf8,' + encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="320">
     <rect width="240" height="320" fill="#fff"/>
     <text x="20" y="60" font-family="Georgia" font-size="22" fill="#1B2A4A">a)  n × 4</text>
     <text x="20" y="110" font-family="Georgia" font-size="22" fill="#1B2A4A">b)  n × 4</text>
     <text x="20" y="160" font-family="Georgia" font-size="22" fill="#1B2A4A">c)  n × 4</text>
   </svg>`,
);

export const PHASE_4_DEMO: Phase4Review = {
  student_id: 'ST003',
  topic_id: 'ALG-KS3-01',
  topic_title: 'What Is Algebra?',
  topic_outcome: {
    mastery_status: 'NEARLY_MASTERED',
    recommended_next_action: 'COMPLETE_TOPIC',
  },

  question_journey: [
    { question_id: 'Q-T01-001', question_text: 'Find a rule for 2 + 4, 5 + 4, 8 + 4.', evaluation: 'CORRECT', review_item_id: null },
    { question_id: 'Q-T01-002', question_text: 'Find a rule for 3 + 4, 9 + 4, 14 + 4.', evaluation: 'WRONG', review_item_id: 'REV-001' },
    { question_id: 'Q-T01-003', question_text: 'A temperature t falls by 3. Write the new temperature.', evaluation: 'WRONG', review_item_id: 'REV-002' },
    // The post-repair attempt at the same question. Correct, so no replay —
    // but it is what recent_improvement_summary below is built from.
    { question_id: 'Q-T01-003', question_text: 'A temperature t falls by 3. Write the new temperature.', evaluation: 'CORRECT', review_item_id: null },
    { question_id: 'Q-T01-004', question_text: 'Find a rule for 10 + 4, 15 + 4, 20 + 4.', evaluation: 'CORRECT', review_item_id: null },
  ],

  tutor_replays: [
    {
      review_item_id: 'REV-001',
      question_id: 'Q-T01-002',
      attempt_id: 'ATTEMPT-018',
      artifact_id: 'ART-P3-000122',
      question_text: 'Find a rule for 3 + 4, 9 + 4, 14 + 4. Write your answer using a letter.',
      first_error: {
        summary: 'The first error was treating the 4 as something to multiply by.',
        student_page_no: 1,
      },
      replay_steps: [
        { sequence_no: 1, narration: 'Let us look at what changes and what stays the same.', tutor_write: 'What changes?' },
        { sequence_no: 2, narration: 'The starting number changes each time — 3, then 9, then 14.', tutor_write: '3, 9, 14  →  changes' },
        { sequence_no: 3, narration: 'The four never changes, and neither does the operation.', tutor_write: '+ 4  →  stays the same' },
        { sequence_no: 4, narration: 'So we add four to a starting number we can call n.', tutor_write: 'Rule:  n + 4' },
      ],
      work_artifact: {
        artifact_id: 'ART-P3-000122',
        page_count: 1,
        pages: [{ page_no: 1, image_url: PAGE }],
        pdf_url: null,
      },
    },
    {
      review_item_id: 'REV-002',
      question_id: 'Q-T01-003',
      attempt_id: 'ATTEMPT-021',
      artifact_id: 'ART-P3-000124',
      question_text: 'A temperature t falls by 3 degrees. Write the new temperature.',
      first_error: {
        summary: 'The first error started when "falls by 3" was treated as addition.',
        student_page_no: 2,
      },
      replay_steps: [
        { sequence_no: 1, narration: 'You correctly started with t as the original temperature.', tutor_write: 'Start:  t' },
        { sequence_no: 2, narration: 'The word falls tells us the value goes down, not up.', tutor_write: 'falls by 3  →  subtract 3' },
        { sequence_no: 3, narration: 'So we subtract three from the starting value.', tutor_write: 't − 3' },
      ],
      work_artifact: {
        artifact_id: 'ART-P3-000124',
        page_count: 2,
        pages: [
          { page_no: 1, image_url: PAGE },
          { page_no: 2, image_url: PAGE },
        ],
        pdf_url: null,
      },
    },
  ],

  student_insights: {
    strength_summary: 'You identified the changing quantity and kept the fixed number in place across several independent questions.',
    development_summary: 'Choosing the operation from the words in the question, particularly words like falls or loses.',
    learning_pattern_summary: 'You wrote a multiplication in three different questions where the numbers were being added.',
    recent_improvement_summary: 'You first used addition for a decrease, then used subtraction correctly on your own after extra practice.',
    next_practice_focus: 'Before writing the expression, decide whether the quantity increases or decreases.',
    personalised_notes: [
      'You correctly identified the changing starting number.',
      'Check the operation carefully when translating a pattern into a rule.',
      'Adding 4 each time gives n + 4, not 4n.',
      'You corrected this idea on the later independent question.',
    ],
  },
};
