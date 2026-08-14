/**
 * Fixture data — mirrors the worked example in the spec (Topic T02, KS3 Algebra,
 * micro-skills T02.M1/M5/M8, coverage grid from §14). Used by the mock adapter so
 * the whole portal runs and demos before the backend authoring API exists.
 */
import type {
  CoverageGrid,
  DashboardStats,
  TopicSummary,
  TopicWorkspace,
} from './contracts';

export const TOPICS: TopicSummary[] = [
  {
    topic_id: 'ALG-ORI-02',
    topic_code: 'T02',
    topic_title: 'Reading n + 5 as a Rule',
    ks_stage: 'KS3',
    completion_pct: 86,
    coverage: { diagnostic: '8/8', guided: '8/8', independent: '6/8' },
    validation: 'amber',
    status: 'IN_REVIEW',
    updated_at: '2026-07-20T14:32:00Z',
    updated_by: 'A. Khan',
    blocking_errors: 0,
    warnings: 3,
  },
  {
    topic_id: 'ALG-ORI-01',
    topic_code: 'T01',
    topic_title: 'What is Algebra?',
    ks_stage: 'KS3',
    completion_pct: 100,
    coverage: { diagnostic: '7/7', guided: '5/5', independent: '4/4' },
    validation: 'green',
    status: 'PUBLISHED',
    updated_at: '2026-07-18T10:21:00Z',
    updated_by: 'A. Khan',
    blocking_errors: 0,
    warnings: 0,
  },
  {
    topic_id: 'ALG-ORI-03',
    topic_code: 'T03',
    topic_title: 'Variables and Constants',
    ks_stage: 'KS3',
    completion_pct: 54,
    coverage: { diagnostic: '5/9', guided: '3/9', independent: '1/9' },
    validation: 'red',
    status: 'DRAFT',
    updated_at: '2026-07-21T09:05:00Z',
    updated_by: 'M. Arya',
    blocking_errors: 4,
    warnings: 6,
  },
  {
    topic_id: 'NUM-FRA-01',
    topic_code: 'T11',
    topic_title: 'Equivalent Fractions',
    ks_stage: 'KS4',
    completion_pct: 72,
    coverage: { diagnostic: '6/6', guided: '4/6', independent: '3/6' },
    validation: 'amber',
    status: 'APPROVED',
    updated_at: '2026-07-15T16:40:00Z',
    updated_by: 'R. Iyer',
    blocking_errors: 0,
    warnings: 2,
  },
];

export const STATS: DashboardStats = {
  topics: 4,
  micro_skills: 31,
  diagnostic_questions: 26,
  guided_questions: 20,
  independent_questions: 14,
  misconceptions: 18,
  scaffolds: 9,
  blocking_errors: 4,
  warnings: 11,
};

const now = '2026-07-20T14:32:00Z';

export const WORKSPACE_T02: TopicWorkspace = {
  details: {
    topic_id: 'ALG-ORI-02',
    topic_code: 'T02',
    topic_title: 'Reading n + 5 as a Rule',
    ks_stage: 'KS3',
    subject: 'Mathematics',
    sequence_no: 2,
    learning_goal:
      'The student can read an expression such as n + 5 as a general rule that adds five to any number, rather than as a single arithmetic sum.',
    core_message: 'A letter stands for any number, and the expression describes what to do to it.',
    status: 'ACTIVE',
    lifecycle: 'IN_REVIEW',
    version: 3,
    created_at: '2026-05-10T10:21:00Z',
    updated_at: now,
  },
  tree: {
    id: 'ALG-ORI-02',
    kind: 'topic',
    label: 'T02 · Reading n + 5 as a Rule',
    status: 'IN_REVIEW',
    children: [
      { id: 'details', kind: 'details', label: 'Topic Details', route: 'details', addable: false },
      { id: 'scope', kind: 'scope-source', label: 'Scope & Source', route: 'scope-source', addable: false },
      {
        id: 'micro-skills',
        kind: 'micro-skills',
        label: 'Micro-skills',
        route: 'micro-skills',
        count: 7,
        addable: true,
        children: [
          { id: 'T02.M1', kind: 'micro-skill', label: 'M1 · Recognise arithmetic vs algebra', route: 'micro-skills?focus=T02.M1', status: 'PUBLISHED' },
          { id: 'T02.M5', kind: 'micro-skill', label: 'M5 · Identify the changing number', route: 'micro-skills?focus=T02.M5', status: 'PUBLISHED' },
          { id: 'T02.M8', kind: 'micro-skill', label: 'M8 · Read n + 5 as a rule', route: 'micro-skills?focus=T02.M8', status: 'PUBLISHED' },
        ],
      },
      {
        id: 'orientation',
        kind: 'orientation',
        label: 'Orientation',
        route: 'orientation',
        count: 2,
        addable: true,
        children: [
          { id: 'ori-video', kind: 'group', label: 'Video · 3 scenes', route: 'orientation' },
          { id: 'ori-cards', kind: 'group', label: 'Support Cards · 2', route: 'orientation' },
        ],
      },
      { id: 'worked-examples', kind: 'worked-examples', label: 'Worked Examples', route: 'worked-examples', count: 1, addable: true },
      {
        id: 'questions',
        kind: 'questions',
        label: 'Questions',
        route: 'questions',
        count: 22,
        addable: true,
        children: [
          { id: 'phase-0', kind: 'phase', label: 'Phase 0 · Diagnostic', route: 'questions?phase=0', count: 8, addable: true },
          { id: 'phase-2', kind: 'phase', label: 'Phase 2 · Guided Learning', route: 'questions?phase=2', count: 8, addable: true },
          { id: 'phase-3', kind: 'phase', label: 'Phase 3 · Independent Practice', route: 'questions?phase=3', count: 6, addable: true },
        ],
      },
      { id: 'misconceptions', kind: 'misconceptions', label: 'Misconceptions', route: 'misconceptions', count: 5, addable: true },
      { id: 'hints-cues', kind: 'hints-cues', label: 'Hints & Visual Cues', route: 'hints-cues', count: 12, addable: true },
      { id: 'scaffolds', kind: 'scaffolds', label: 'Scaffolds & Parallel Examples', route: 'scaffolds', count: 4, addable: true },
      { id: 'coverage', kind: 'coverage', label: 'Coverage & Validation', route: 'coverage', addable: false },
      { id: 'publish', kind: 'publish', label: 'Preview & Publish', route: 'publish', addable: false },
    ],
  },
  coverage_summary: [
    { label: 'Micro-skills', have: 7, need: 7, state: 'ok' },
    { label: 'Diagnostic Questions', have: 8, need: 8, state: 'ok' },
    { label: 'Worked Examples', have: 1, need: 1, state: 'ok' },
    { label: 'Guided Practice', have: 8, need: 8, state: 'ok' },
    { label: 'Independent Practice', have: 6, need: 8, state: 'warn' },
  ],
  micro_skills: [
    { micro_skill_id: 'ALG.KS3.T02.M1', skill_code: 'M1', skill_name: 'Recognise arithmetic vs algebra', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 2, independent: 2, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { micro_skill_id: 'ALG.KS3.T02.M5', skill_code: 'M5', skill_name: 'Identify the changing number', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:31:00Z' },
    { micro_skill_id: 'ALG.KS3.T02.M8', skill_code: 'M8', skill_name: 'Read n + 5 as a rule', status: 'PUBLISHED', diagnostic: 1, worked: 1, guided: 1, independent: 1, hints: 2, updated_at: '2026-05-10T14:32:00Z' },
  ],
  validation: [
    { id: 'v1', severity: 'warning', message: 'M5 has only one independent question — a fresh rescue retry may be unavailable.', node_route: 'coverage' },
    { id: 'v2', severity: 'warning', message: 'M8 independent questions use only one item family, limiting reasoning diversity.', node_route: 'coverage' },
    { id: 'v3', severity: 'warning', message: 'Approved content has a pending source review (Scope & Source).', node_route: 'scope-source' },
  ],
};

export const COVERAGE_GRID_T02: CoverageGrid = {
  columns: [
    { id: 'diagnostic', label: 'Diagnostic' },
    { id: 'worked', label: 'Worked Example' },
    { id: 'guided', label: 'Guided' },
    { id: 'independent', label: 'Independent' },
    { id: 'families', label: 'Indep. Families' },
    { id: 'errors', label: 'Errors' },
    { id: 'misconceptions', label: 'Misconceptions' },
    { id: 'hints', label: 'Hints' },
    { id: 'cues', label: 'Visual Cues' },
    { id: 'scaffolds', label: 'Scaffolds' },
    { id: 'parallel', label: 'Parallel Ex.' },
  ],
  rows: [
    {
      micro_skill_id: 'T02.M1',
      cells: {
        diagnostic: { count: 1, state: 'ok' }, worked: { count: 1, state: 'ok' }, guided: { count: 2, state: 'ok' }, independent: { count: 2, state: 'ok' }, families: { count: 2, state: 'ok' }, errors: { count: 2, state: 'ok' }, misconceptions: { count: 1, state: 'ok' }, hints: { count: 2, state: 'ok' }, cues: { count: 1, state: 'ok' }, scaffolds: { count: 1, state: 'ok' }, parallel: { count: 1, state: 'ok' },
      },
    },
    {
      micro_skill_id: 'T02.M5',
      cells: {
        diagnostic: { count: 1, state: 'ok' }, worked: { count: 1, state: 'ok' }, guided: { count: 1, state: 'ok' }, independent: { count: 1, state: 'warn' }, families: { count: 1, state: 'warn' }, errors: { count: 1, state: 'ok' }, misconceptions: { count: 1, state: 'ok' }, hints: { count: 2, state: 'ok' }, cues: { count: 1, state: 'ok' }, scaffolds: { count: 1, state: 'ok' }, parallel: { count: 1, state: 'ok' },
      },
    },
    {
      micro_skill_id: 'T02.M8',
      cells: {
        diagnostic: { count: 1, state: 'ok' }, worked: { count: 1, state: 'ok' }, guided: { count: 1, state: 'ok' }, independent: { count: 1, state: 'ok' }, families: { count: 1, state: 'warn' }, errors: { count: 2, state: 'ok' }, misconceptions: { count: 1, state: 'ok' }, hints: { count: 2, state: 'ok' }, cues: { count: 1, state: 'ok' }, scaffolds: { count: 1, state: 'ok' }, parallel: { count: 0, state: 'missing' },
      },
    },
  ],
};
