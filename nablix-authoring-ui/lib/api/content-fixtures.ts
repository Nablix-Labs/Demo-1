/**
 * Section content fixtures for Topic T02 (spec §6–§15). Representative data so
 * every authoring screen renders with realistic content before the backend ships.
 */
import type { TopicContent } from './contracts';

export const CONTENT_T02: TopicContent = {
  scope: [
    { scope_item_id: 'SC-01', scope_type: 'INCLUDED', item_text: 'Reading a single-operation expression such as n + 5 as a general rule.', active: true },
    { scope_item_id: 'SC-02', scope_type: 'INCLUDED', item_text: 'Substituting whole numbers into n + 5 to generate outputs.', active: true },
    { scope_item_id: 'SC-03', scope_type: 'EXCLUDED', item_text: 'Two-step expressions such as 2n + 5 or n² + 5.', active: true },
    { scope_item_id: 'SC-04', scope_type: 'EXCLUDED', item_text: 'Solving equations for n (introduced in T05).', active: true },
  ],
  source: {
    source_type: 'NABLIX_AUTHORED',
    source_name: 'Nablix KS3 Algebra Foundations Pack',
    license_name: 'OWNED_ORIGINAL_CONTENT',
    adapted: false,
    direct_text_copied: false,
    review_status: 'PENDING_FINAL_REVIEW',
  },
  micro_skills: [
    { micro_skill_id: 'ALG.KS3.T02.M1', skill_code: 'M1', skill_name: 'Recognise arithmetic vs algebra', description: 'Tell apart a fixed arithmetic sum (3 + 5) from an algebraic rule (n + 5) that works for any number.', assessment_priority: 'HIGH', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 2, independent: 2, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { micro_skill_id: 'ALG.KS3.T02.M5', skill_code: 'M5', skill_name: 'Identify the changing number', description: 'Point to the letter as the value that can change, and the constant as the part that stays the same.', prerequisite: 'ALG.KS3.T02.M1', assessment_priority: 'MEDIUM', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { micro_skill_id: 'ALG.KS3.T02.M8', skill_code: 'M8', skill_name: 'Read n + 5 as a rule', description: 'Interpret n + 5 aloud as "add five to any number" and apply it to produce outputs.', prerequisite: 'ALG.KS3.T02.M5', assessment_priority: 'HIGH', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:32:00Z' },
  ],
  orientation_video: {
    video_title: 'What does n + 5 really mean?',
    duration_sec: 95,
    status: 'APPROVED',
    scenes: [
      { scene_no: 1, scene_title: 'A number that can change', duration_sec: 30, visual_action: 'A box labelled n cycles through 1, 2, 3 while a “+5” tag stays fixed beside it.', narration_text: 'Here is a number that can change. We call it n. Whatever n is, we add five to it.', on_screen_text: 'n + 5' },
      { scene_no: 2, scene_title: 'Trying some values', duration_sec: 35, visual_action: 'Three quick substitutions animate: 1→6, 2→7, 10→15.', narration_text: 'If n is one, we get six. If n is two, we get seven. The rule never changes.', on_screen_text: '1 → 6 · 2 → 7 · 10 → 15' },
      { scene_no: 3, scene_title: 'A rule, not a sum', duration_sec: 30, visual_action: 'Split screen: 3 + 5 = 8 (fixed) vs n + 5 (a machine).', narration_text: 'Three plus five is just one answer. n plus five is a rule that works for every number.', on_screen_text: 'n + 5 is a rule' },
    ],
  },
  support_cards: [
    { support_card_id: 'SUP-01', card_title: 'The letter is a placeholder', visual_content: 'n  □ + 5', narration_or_text: 'The letter simply holds a space for any number you choose.', status: 'APPROVED' },
    { support_card_id: 'SUP-02', card_title: 'Say it out loud', visual_content: '“add five to any number”', narration_or_text: 'Reading the rule aloud makes the operation obvious.', status: 'DRAFT' },
  ],
  worked_examples: [
    {
      worked_example_id: 'WE-T02-01',
      title: 'Building the n + 5 rule from a pattern',
      problem_statement: 'A locker number is always five more than the shelf number n. Write the rule and find the locker for shelf 12.',
      final_answer: 'Rule: n + 5. For n = 12, locker = 17.',
      status: 'APPROVED',
      steps: [
        { step_no: 1, screen_content: 'Shelf 1 → locker 6, shelf 2 → locker 7', narration_text: 'Notice each locker is five more than its shelf.', must_show: 'the +5 gap' },
        { step_no: 2, screen_content: 'Let the shelf be n. Then locker = n + 5.', narration_text: 'We replace the changing number with a letter.', must_show: 'letter substitution' },
        { step_no: 3, screen_content: 'n = 12 → 12 + 5 = 17', narration_text: 'Now the rule works for any shelf, including twelve.', must_not_show: 'solving for n' },
      ],
      skill_mappings: [
        { micro_skill_id: 'ALG.KS3.T02.M8', weight: 1.0, is_primary: true },
        { micro_skill_id: 'ALG.KS3.T02.M5', weight: 0.5, is_primary: false },
      ],
    },
  ],
  questions: [
    { question_id: 'Q-T02-001', question_text: 'Which of these is an algebraic rule rather than a single sum?', question_type: 'SINGLE_CHOICE', difficulty: 1, item_family_id: 'FAM-T02-ARITH-VS-ALGEBRA', phase: 'PHASE_0_DIAGNOSTIC', question_role: 'DIAGNOSTIC', status: 'PUBLISHED', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T02.M1', weight: 1.0, is_primary: true }], canonical_answer: 'n + 5', verification_method: 'EXACT_CHOICE_MATCH' },
    { question_id: 'Q-T02-014', question_text: 'A rule adds 5 to any number n. Write the rule, then find the result when n = 9.', question_type: 'SHORT_RESPONSE', difficulty: 1, item_family_id: 'FAM-T02-ENCODE-ADD-CONSTANT', phase: 'PHASE_2_GUIDED_LEARNING', question_role: 'CLOSE_PRACTICE', status: 'PUBLISHED', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T02.M8', weight: 1.0, is_primary: true }, { micro_skill_id: 'ALG.KS3.T02.M5', weight: 0.5, is_primary: false }], canonical_answer: 'n + 5; 14', verification_method: 'STRUCTURED_TEXT_AND_SYMBOLIC_MATCH' },
    { question_id: 'Q-T02-021', question_text: 'The cost in pounds is the number of tickets t plus a £5 booking fee. Write the rule and evaluate for 8 tickets.', question_type: 'SHORT_RESPONSE', difficulty: 2, item_family_id: 'FAM-T02-INTERPRET-CONTEXT', phase: 'PHASE_3_INDEPENDENT_PRACTICE', question_role: 'INDEPENDENT_VERIFICATION', status: 'DRAFT', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T02.M8', weight: 1.0, is_primary: true }], canonical_answer: 't + 5; 13', verification_method: 'STRUCTURED_TEXT_AND_SYMBOLIC_MATCH' },
  ],
  error_types: [
    { error_code: 'ERR-ADD-BEFORE-VAR', error_name: 'Evaluates constant before knowing n', description: 'Student computes a fixed value (e.g. writes 5) instead of keeping the rule n + 5.', severity: 'HIGH', detection_method: 'STRUCTURED_EXPRESSION_MATCH', active: true },
    { error_code: 'ERR-DROP-LETTER', error_name: 'Drops the variable', description: 'Student writes only the constant, omitting the letter entirely.', severity: 'MEDIUM', detection_method: 'TOKEN_PATTERN', active: true },
  ],
  misconceptions: [
    {
      misconception_id: 'MIS-T02-01',
      name: 'A letter must have one fixed value',
      description: 'The student believes n stands for a single unknown number to be found, not a placeholder for any number.',
      diagnosis_rule: 'Triggered when the student substitutes a single value and treats n + 5 as having one “right” answer.',
      active: true,
      error_links: ['ERR-ADD-BEFORE-VAR'],
      skill_links: [
        { micro_skill_id: 'ALG.KS3.T02.M8', relationship_type: 'DIRECT_FAILURE' },
        { micro_skill_id: 'ALG.KS3.T02.M1', relationship_type: 'UNDERLYING_GAP' },
      ],
    },
    {
      misconception_id: 'MIS-T02-02',
      name: 'The operation sign can be ignored',
      description: 'The student reads n + 5 as just “n and 5” without applying the addition.',
      diagnosis_rule: 'Triggered when the output equals n or 5 rather than their sum.',
      active: true,
      error_links: ['ERR-DROP-LETTER'],
      skill_links: [{ micro_skill_id: 'ALG.KS3.T02.M5', relationship_type: 'AFFECTED_SKILL' }],
    },
  ],
  hints: [
    { hint_id: 'H-01', hint_level: 1, hint_type: 'ATTENTION', content: 'What part of n + 5 is allowed to change?', active: true },
    { hint_id: 'H-02', hint_level: 2, hint_type: 'CONCEPT_REMINDER', content: 'The letter is a placeholder — the rule works for every number.', active: true },
    { hint_id: 'H-03', hint_level: 3, hint_type: 'PARTIAL_STEP', content: 'Start by writing n, then add five: n + 5.', active: true },
  ],
  visual_cues: [
    { visual_cue_id: 'VC-01', cue_name: 'Number machine adds five', cue_purpose: 'Shows n entering a machine and exiting as n + 5 to reinforce the rule idea.', retrieval_keywords: ['function machine', 'add five', 'placeholder'], embedding_status: 'PENDING', review_status: 'APPROVED', status: 'APPROVED' },
    { visual_cue_id: 'VC-02', cue_name: 'Placeholder box for n', cue_purpose: 'Highlights the letter as an empty box that any number can fill.', retrieval_keywords: ['placeholder', 'variable box'], embedding_status: 'PENDING', review_status: 'APPROVED', status: 'DRAFT' },
  ],
  scaffolds: [
    {
      scaffold_id: 'SCF-T02-01',
      scaffold_name: 'Rebuild the rule from one value',
      trigger_rule: 'Activate when the student gives a single number instead of an expression.',
      completion_rule: 'Student writes n + 5 and evaluates one substitution correctly.',
      active: true,
      steps: [
        { stage_no: 1, prompt: 'You picked one number. Can the shelf be a different number too?', expected_response: 'Yes', next_on_correct: 'STAGE_2', next_on_incorrect: 'HINT' },
        { stage_no: 2, prompt: 'Use a letter for the changing number. What do we add?', expected_response: 'n + 5', next_on_correct: 'COMPLETE', next_on_incorrect: 'VISUAL_CUE' },
      ],
    },
  ],
  parallel_examples: [
    { parallel_example_id: 'PE-01', misconception_id: 'MIS-T02-01', problem_statement: 'A bus arrives 5 minutes after time m. Write the rule and find the arrival for m = 20.', final_answer: 'm + 5; 25', active: true },
  ],
};
