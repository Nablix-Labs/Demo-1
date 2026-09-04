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

// The real artifact is a stored PDF; the dev screen has no storage service, so
// the viewer shows its unavailable state. That is the honest fixture — inventing
// a PDF here would demo a panel that behaves differently from the real one.
const NO_PDF = '';

export const PHASE_4_DEMO: Phase4Review = {
  student_id: 'ST003',
  topic_id: 'ALG-KS3-01',
  topic_title: 'What Is Algebra?',
  topic_outcome: {
    mastery_status: 'NEARLY_MASTERED',
    recommended_next_action: 'COMPLETE_TOPIC',
    next_action_message:
      'Great progress! You are nearly there. Complete the remaining question to finish this topic.',
  },

  question_journey: [
    { question_id: 'Q-T01-001', question_text: 'Find a rule for 2 + 4, 5 + 4, 8 + 4.', skill_label: 'Add a fixed number', evaluation: 'CORRECT', review_item_id: null },
    // The third state: answered in part. No replay — a partial answer is not a
    // wrong submission, and §3 gives replays to wrong submissions only.
    { question_id: 'Q-T01-005', question_text: 'Find a rule for 6 + 4, 11 + 4.', skill_label: 'Add a fixed number', evaluation: 'PARTIAL', review_item_id: null },
    { question_id: 'Q-T01-002', question_text: 'Find a rule for 3 + 4, 9 + 4, 14 + 4.', skill_label: 'Find a rule', evaluation: 'WRONG', review_item_id: 'REV-001' },
    { question_id: 'Q-T01-003', question_text: 'A temperature t falls by 3. Write the new temperature.', skill_label: 'Multiply pattern', evaluation: 'WRONG', review_item_id: 'REV-002' },
    // The post-repair attempt at the same question. Correct, so no replay —
    // but it is what recent_improvement_summary below is built from.
    { question_id: 'Q-T01-003', question_text: 'A temperature t falls by 3. Write the new temperature.', skill_label: 'Write an expression', evaluation: 'CORRECT', review_item_id: null },
    { question_id: 'Q-T01-004', question_text: 'Find a rule for 10 + 4, 15 + 4, 20 + 4.', skill_label: 'Add a fixed number', evaluation: 'CORRECT', review_item_id: null },
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
        why_it_matters:
          'Multiplication changes the size. We need the pattern to increase by the same amount.',
        student_page_no: 1,
      },
      replay_steps: [
        // Boards from PR #257. Narration is short on purpose now: the board
        // carries the mathematics, and these fixtures follow that instruction
        // so the screen is reviewed the way real payloads will render.
        {
          sequence_no: 1, stage_label: 'Spot the pattern', duration_ms: 21000,
          narration: 'Look at how each number changes.',
          tutor_write: 'What changes?',
          board: {
            elements: [
              { kind: 'value_row', values: ['2', '5', '8'], arrow_label: 'changes' },
            ],
          },
        },
        {
          sequence_no: 2, stage_label: 'Spot the pattern', duration_ms: 24000,
          narration: 'Each one goes up by the same four.',
          tutor_write: '+ 4 each time',
          board: {
            elements: [
              { kind: 'value_row', values: ['2', '5', '8'], arrow_label: 'changes' },
              { kind: 'brace', over: 'value_row', labels: ['+ 4', '+ 4', '+ 4'] },
              { kind: 'brace', over: 'brace', labels: ['stays the same'] },
            ],
          },
        },
        {
          sequence_no: 3, stage_label: 'Find the error', duration_ms: 33000,
          narration: 'Multiplying changes the size instead.',
          tutor_write: 'Not n × 4',
          board: {
            elements: [
              { kind: 'struck', text: 'n × 4', tone: 'error' },
              { kind: 'label', text: 'multiplying changes the size' },
            ],
          },
        },
        {
          sequence_no: 4, stage_label: 'Build the rule', duration_ms: 30000,
          narration: 'So the rule adds four to any starting number.',
          tutor_write: 'Rule:  n + 4',
          board: {
            elements: [
              { kind: 'struck', text: 'n × 4', tone: 'error' },
              { kind: 'boxed', text: 'Rule:  n + 4', tone: 'correct' },
              { kind: 'example', text: 'Try n = 6:\n6 + 4 = 10' },
            ],
          },
        },
      ],
      work_artifact: {
        artifact_id: 'ART-P3-000122',
        page_count: 1,
        pdf_url: NO_PDF,
        // A stand-in for the flat snapshot the backend does not send yet, so
        // the panel and its error ring can be seen and reviewed. Inline SVG
        // rather than a checked-in binary: a few hundred bytes, and obviously
        // a fixture rather than a real student's handwriting.
        snapshot_image_url: 'data:image/svg+xml;utf8,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%20200%20150%22%3E%3Crect%20width=%22200%22%20height=%22150%22%20fill=%22white%22/%3E%3Cg%20stroke=%22%23c8d0dd%22%20stroke-width=%220.6%22%3E%3Cline%20x1=%220%22%20y1=%2238%22%20x2=%22200%22%20y2=%2238%22/%3E%3Cline%20x1=%220%22%20y1=%2276%22%20x2=%22200%22%20y2=%2276%22/%3E%3Cline%20x1=%220%22%20y1=%22114%22%20x2=%22200%22%20y2=%22114%22/%3E%3C/g%3E%3Ctext%20x=%2222%22%20y=%2230%22%20font-family=%22cursive%22%20font-size=%2214%22%20fill=%22%231e2a3a%22%3EFind%20a%20rule%3C/text%3E%3Ctext%20x=%2258%22%20y=%2288%22%20font-family=%22cursive%22%20font-size=%2226%22%20fill=%22%231e2a3a%22%3En%20%C3%97%204%3C/text%3E%3C/svg%3E',
        // The wrong expression, ringed where it sits on the page.
        error_regions: [{ x: 0.24, y: 0.38, w: 0.46, h: 0.26, tone: 'error' as const }],
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
        why_it_matters:
          'A fall makes the value smaller. Adding would move the temperature the wrong way.',
        student_page_no: 2,
      },
      // Deliberately UNTIMED and unlabelled, so the fixture exercises the
      // fallbacks: this replay must render numbered steps and no clock, beside
      // one that renders named stages and a clock.
      replay_steps: [
        { sequence_no: 1, narration: 'You correctly started with t as the original temperature.', tutor_write: 'Start:  t' },
        { sequence_no: 2, narration: 'The word falls tells us the value goes down, not up.', tutor_write: 'falls by 3  →  subtract 3' },
        { sequence_no: 3, narration: 'So we subtract three from the starting value.', tutor_write: 't − 3' },
      ],
      work_artifact: { artifact_id: 'ART-P3-000124', page_count: 2, pdf_url: NO_PDF },
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

  error_pattern: {
    signature: 'n × 4',
    occurrence_count: 2,
    question_ids: ['Q-T01-002', 'Q-T01-003'],
  },
};
