/**
 * Cross-topic library fixtures for the top-level nav (Curriculum, global
 * Micro-skills/Questions/Hints/etc., Review, Settings). Spans several topics so
 * the libraries look populated; the mock adapter serves these.
 */
import type { CurriculumNode, GlobalLibrary, ReviewItem, SettingsData } from './contracts';

const T = {
  t02: { topic_id: 'ALG-ORI-02', topic_code: 'T02' },
  t01: { topic_id: 'ALG-ORI-01', topic_code: 'T01' },
  t03: { topic_id: 'ALG-ORI-03', topic_code: 'T03' },
  t11: { topic_id: 'NUM-FRA-01', topic_code: 'T11' },
};

export const LIBRARY: GlobalLibrary = {
  micro_skills: [
    { ...T.t01, micro_skill_id: 'ALG.KS3.T01.M1', skill_code: 'M1', skill_name: 'Define a variable', description: 'State that a letter represents a number.', assessment_priority: 'HIGH', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 2, independent: 2, hints: 2, updated_at: '2026-05-08T10:00:00Z' },
    { ...T.t02, micro_skill_id: 'ALG.KS3.T02.M1', skill_code: 'M1', skill_name: 'Recognise arithmetic vs algebra', description: 'Tell a fixed sum from an algebraic rule.', assessment_priority: 'HIGH', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 2, independent: 2, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { ...T.t02, micro_skill_id: 'ALG.KS3.T02.M5', skill_code: 'M5', skill_name: 'Identify the changing number', description: 'Point to the variable vs the constant.', prerequisite: 'ALG.KS3.T02.M1', assessment_priority: 'MEDIUM', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { ...T.t02, micro_skill_id: 'ALG.KS3.T02.M8', skill_code: 'M8', skill_name: 'Read n + 5 as a rule', description: 'Interpret n + 5 as “add five to any number”.', prerequisite: 'ALG.KS3.T02.M5', assessment_priority: 'HIGH', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:32:00Z' },
    { ...T.t03, micro_skill_id: 'ALG.KS3.T03.M2', skill_code: 'M2', skill_name: 'Distinguish variable and constant', description: 'Classify terms as variable or constant.', assessment_priority: 'MEDIUM', status: 'DRAFT', diagnostic: 1, worked: 0, guided: 1, independent: 0, hints: 1, updated_at: '2026-07-21T09:05:00Z' },
    { ...T.t11, micro_skill_id: 'NUM.KS4.T11.M4', skill_code: 'M4', skill_name: 'Scale numerator and denominator', description: 'Multiply top and bottom by the same factor.', assessment_priority: 'HIGH', status: 'APPROVED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-07-15T16:40:00Z' },
  ],
  questions: [
    { ...T.t02, question_id: 'Q-T02-001', question_text: 'Which of these is an algebraic rule rather than a single sum?', question_type: 'SINGLE_CHOICE', difficulty: 1, item_family_id: 'FAM-T02-ARITH-VS-ALGEBRA', phase: 'PHASE_0_DIAGNOSTIC', question_role: 'DIAGNOSTIC', status: 'PUBLISHED', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T02.M1', weight: 1, is_primary: true }], canonical_answer: 'n + 5', verification_method: 'EXACT_CHOICE_MATCH' },
    { ...T.t02, question_id: 'Q-T02-014', question_text: 'A rule adds 5 to any number n. Write the rule, then find the result when n = 9.', question_type: 'SHORT_RESPONSE', difficulty: 1, item_family_id: 'FAM-T02-ENCODE-ADD-CONSTANT', phase: 'PHASE_2_GUIDED_LEARNING', question_role: 'CLOSE_PRACTICE', status: 'PUBLISHED', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T02.M8', weight: 1, is_primary: true }], canonical_answer: 'n + 5; 14', verification_method: 'STRUCTURED_TEXT_AND_SYMBOLIC_MATCH' },
    { ...T.t01, question_id: 'Q-T01-003', question_text: 'What does the letter x represent in 3x?', question_type: 'CHOICE_WITH_EXPLANATION', difficulty: 1, item_family_id: 'FAM-T01-VARIABLE-MEANING', phase: 'PHASE_0_DIAGNOSTIC', question_role: 'DIAGNOSTIC', status: 'PUBLISHED', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T01.M1', weight: 1, is_primary: true }], canonical_answer: 'any number', verification_method: 'CHOICE_AND_CONCEPT_MATCH' },
    { ...T.t11, question_id: 'Q-T11-007', question_text: 'Write a fraction equivalent to 2/3 with denominator 12.', question_type: 'SHORT_RESPONSE', difficulty: 2, item_family_id: 'FAM-T11-SCALE-FRACTION', phase: 'PHASE_3_INDEPENDENT_PRACTICE', question_role: 'INDEPENDENT_VERIFICATION', status: 'APPROVED', skill_mappings: [{ micro_skill_id: 'NUM.KS4.T11.M4', weight: 1, is_primary: true }], canonical_answer: '8/12', verification_method: 'SYMBOLIC_EQUIVALENCE' },
    { ...T.t03, question_id: 'Q-T03-002', question_text: 'Sort these into variables and constants: x, 7, k, 12.', question_type: 'MULTI_PART_SHORT_RESPONSE', difficulty: 1, item_family_id: 'FAM-T03-CLASSIFY-TERMS', phase: 'PHASE_2_GUIDED_LEARNING', question_role: 'PARTIAL_APPLICATION', status: 'DRAFT', skill_mappings: [{ micro_skill_id: 'ALG.KS3.T03.M2', weight: 1, is_primary: true }], canonical_answer: 'variables: x,k / constants: 7,12', verification_method: 'STRUCTURED_TEXT_MATCH' },
  ],
  hints: [
    { ...T.t02, hint_id: 'H-01', hint_level: 1, hint_type: 'ATTENTION', content: 'What part of n + 5 is allowed to change?', active: true },
    { ...T.t02, hint_id: 'H-02', hint_level: 2, hint_type: 'CONCEPT_REMINDER', content: 'The letter is a placeholder — the rule works for every number.', active: true },
    { ...T.t01, hint_id: 'H-11', hint_level: 1, hint_type: 'ATTENTION', content: 'Does x have to be one fixed number?', active: true },
    { ...T.t11, hint_id: 'H-21', hint_level: 2, hint_type: 'PARTIAL_STEP', content: 'Multiply the top and bottom by the same number.', active: true },
  ],
  misconceptions: [
    { ...T.t02, misconception_id: 'MIS-T02-01', name: 'A letter must have one fixed value', description: 'The student treats n as a single unknown to be found.', diagnosis_rule: 'Substitutes one value and expects a single answer.', active: true, error_links: ['ERR-ADD-BEFORE-VAR'], skill_links: [{ micro_skill_id: 'ALG.KS3.T02.M8', relationship_type: 'DIRECT_FAILURE' }] },
    { ...T.t01, misconception_id: 'MIS-T01-01', name: 'Letters are labels, not numbers', description: 'The student reads x as “x apples” rather than a number.', diagnosis_rule: 'Attaches a unit/object to the variable.', active: true, error_links: ['ERR-DROP-LETTER'], skill_links: [{ micro_skill_id: 'ALG.KS3.T01.M1', relationship_type: 'UNDERLYING_GAP' }] },
    { ...T.t11, misconception_id: 'MIS-T11-02', name: 'Only add to make equivalent fractions', description: 'The student adds instead of multiplying top and bottom.', diagnosis_rule: 'Adds the same number to numerator and denominator.', active: true, error_links: [], skill_links: [{ micro_skill_id: 'NUM.KS4.T11.M4', relationship_type: 'DIRECT_FAILURE' }] },
  ],
  visual_cues: [
    { ...T.t02, visual_cue_id: 'VC-01', cue_name: 'Number machine adds five', cue_purpose: 'n enters a machine and exits as n + 5.', retrieval_keywords: ['function machine', 'add five'], embedding_status: 'PENDING', review_status: 'APPROVED', status: 'APPROVED' },
    { ...T.t01, visual_cue_id: 'VC-11', cue_name: 'Placeholder box', cue_purpose: 'A letter shown as an empty box any number fills.', retrieval_keywords: ['placeholder', 'variable'], embedding_status: 'PENDING', review_status: 'APPROVED', status: 'DRAFT' },
    { ...T.t11, visual_cue_id: 'VC-21', cue_name: 'Scaling a fraction bar', cue_purpose: 'A bar split finer to show equivalence.', retrieval_keywords: ['fraction bar', 'equivalent'], embedding_status: 'PENDING', review_status: 'PENDING', status: 'DRAFT' },
  ],
  scaffolds: [
    { ...T.t02, scaffold_id: 'SCF-T02-01', scaffold_name: 'Rebuild the rule from one value', trigger_rule: 'Student gives a single number instead of an expression.', completion_rule: 'Student writes n + 5 and evaluates one substitution.', active: true, steps: [{ stage_no: 1, prompt: 'Can the shelf be a different number too?', expected_response: 'Yes', next_on_correct: 'STAGE_2', next_on_incorrect: 'HINT' }, { stage_no: 2, prompt: 'Use a letter. What do we add?', expected_response: 'n + 5', next_on_correct: 'COMPLETE', next_on_incorrect: 'VISUAL_CUE' }] },
    { ...T.t11, scaffold_id: 'SCF-T11-01', scaffold_name: 'Scale, don’t add', trigger_rule: 'Student adds to numerator and denominator.', completion_rule: 'Student multiplies both by the same factor.', active: true, steps: [{ stage_no: 1, prompt: 'What did you do to the top? And the bottom?', expected_response: 'multiplied', next_on_correct: 'COMPLETE', next_on_incorrect: 'HINT' }] },
  ],
  error_types: [
    { error_code: 'ERR-ADD-BEFORE-VAR', error_name: 'Evaluates constant before knowing n', description: 'Computes a fixed value instead of keeping the rule.', severity: 'HIGH', detection_method: 'STRUCTURED_EXPRESSION_MATCH', active: true },
    { error_code: 'ERR-DROP-LETTER', error_name: 'Drops the variable', description: 'Writes only the constant, omitting the letter.', severity: 'MEDIUM', detection_method: 'TOKEN_PATTERN', active: true },
    { error_code: 'ERR-ADD-FRACTION', error_name: 'Adds to make equivalent fraction', description: 'Adds instead of scaling numerator and denominator.', severity: 'HIGH', detection_method: 'SYMBOLIC_PATTERN', active: true },
  ],
};

export const CURRICULUM: CurriculumNode[] = [
  {
    id: 'KS3', label: 'KS3', kind: 'stage',
    children: [
      {
        id: 'KS3-ALG', label: 'Algebra', kind: 'subject',
        children: [
          { id: 'ALG-ORI-01', label: 'T01 · What is Algebra?', kind: 'topic', topic_id: 'ALG-ORI-01', status: 'PUBLISHED', children: [{ id: 'T01.M1', label: 'M1 · Define a variable', kind: 'micro-skill', status: 'PUBLISHED' }] },
          { id: 'ALG-ORI-02', label: 'T02 · Reading n + 5 as a Rule', kind: 'topic', topic_id: 'ALG-ORI-02', status: 'IN_REVIEW', children: [
            { id: 'T02.M1', label: 'M1 · Recognise arithmetic vs algebra', kind: 'micro-skill', status: 'PUBLISHED' },
            { id: 'T02.M5', label: 'M5 · Identify the changing number', kind: 'micro-skill', status: 'PUBLISHED' },
            { id: 'T02.M8', label: 'M8 · Read n + 5 as a rule', kind: 'micro-skill', status: 'PUBLISHED' },
          ] },
          { id: 'ALG-ORI-03', label: 'T03 · Variables and Constants', kind: 'topic', topic_id: 'ALG-ORI-03', status: 'DRAFT', children: [{ id: 'T03.M2', label: 'M2 · Distinguish variable and constant', kind: 'micro-skill', status: 'DRAFT' }] },
        ],
      },
    ],
  },
  {
    id: 'KS4', label: 'KS4', kind: 'stage',
    children: [
      {
        id: 'KS4-NUM', label: 'Number', kind: 'subject',
        children: [
          { id: 'NUM-FRA-01', label: 'T11 · Equivalent Fractions', kind: 'topic', topic_id: 'NUM-FRA-01', status: 'APPROVED', children: [{ id: 'T11.M4', label: 'M4 · Scale numerator and denominator', kind: 'micro-skill', status: 'APPROVED' }] },
        ],
      },
    ],
  },
];

export const REVIEW_QUEUE: ReviewItem[] = [
  { topic_id: 'ALG-ORI-02', topic_code: 'T02', topic_title: 'Reading n + 5 as a Rule', ks_stage: 'KS3', submitted_by: 'A. Khan', submitted_at: '2026-07-20T14:32:00Z', status: 'IN_REVIEW', blocking_errors: 0, warnings: 3, changed: '22 questions · 7 micro-skills · 1 worked example' },
  { topic_id: 'NUM-FRA-01', topic_code: 'T11', topic_title: 'Equivalent Fractions', ks_stage: 'KS4', submitted_by: 'R. Iyer', submitted_at: '2026-07-15T16:40:00Z', status: 'APPROVED', blocking_errors: 0, warnings: 2, changed: '14 questions · 6 micro-skills' },
];

export const SETTINGS: SettingsData = {
  reference_sets: [
    { label: 'Question types', description: 'Response formats the builder supports.', values: ['SINGLE_CHOICE', 'SHORT_RESPONSE', 'MULTI_PART_SHORT_RESPONSE', 'CHOICE_WITH_EXPLANATION', 'TRUE_FALSE_WITH_EXPLANATION'] },
    { label: 'Question roles', description: 'Allowed roles, gated by phase.', values: ['DIAGNOSTIC', 'CLOSE_PRACTICE', 'PARTIAL_APPLICATION', 'NEAR_TRANSFER', 'MISCONCEPTION_PROBE', 'FINAL_GUIDED_CHECK', 'INDEPENDENT_VERIFICATION'] },
    { label: 'Verification methods', description: 'How the backend evaluates an answer.', values: ['SYMBOLIC_EQUIVALENCE', 'STRUCTURED_TEXT_MATCH', 'CHOICE_AND_CONCEPT_MATCH', 'STRUCTURED_TEXT_AND_SYMBOLIC_MATCH', 'CONCEPT_TEXT_MATCH', 'EXACT_NOTATION_MATCH', 'BOOLEAN_AND_CONCEPT_MATCH', 'EXACT_CHOICE_MATCH'] },
    { label: 'Detection methods', description: 'How an error pattern is recognised.', values: ['PATTERN_MATCH', 'STRUCTURED_EXPRESSION_MATCH', 'TOKEN_PATTERN', 'SEMANTIC_AND_SYMBOLIC_MATCH', 'SYMBOLIC_PATTERN', 'STRUCTURED_TEXT_MATCH', 'SEMANTIC_CLASSIFICATION', 'CASE_COMPARISON'] },
    { label: 'Relationship types', description: 'How a misconception relates to a skill.', values: ['DIRECT_FAILURE', 'UNDERLYING_GAP', 'AFFECTED_SKILL'] },
    { label: 'KS stages', description: 'Curriculum stages in scope.', values: ['KS3', 'KS4'] },
  ],
};
