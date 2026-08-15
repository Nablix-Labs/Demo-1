/**
 * Authoring API contract — TypeScript mirror of the endpoints in the Frontend
 * Specification §16. The UI codes against THIS; a mock adapter serves it today
 * and an HTTP adapter serves it from the real backend once those endpoints ship.
 *
 * IDs and timestamps are backend-generated (spec §16.1) — the UI never mints them.
 */

// ── Enums / status vocabularies ───────────────────────────────────────────
export type LifecycleStatus =
  | 'DRAFT'
  | 'IN_REVIEW'
  | 'APPROVED'
  | 'PUBLISHED'
  | 'ARCHIVED';

export type ActivityStatus = 'ACTIVE' | 'INACTIVE';
export type ValidationState = 'green' | 'amber' | 'red';
export type KsStage = 'KS3' | 'KS4';

/** Coverage cell state — spec §14 indicators. */
export type CoverageState = 'ok' | 'warn' | 'missing'; // ✓ / ⚠ / ✕

// ── Dashboard (§4) ────────────────────────────────────────────────────────
export interface TopicSummary {
  topic_id: string;
  topic_code: string;
  topic_title: string;
  ks_stage: KsStage;
  completion_pct: number; // mandatory-content completion
  coverage: {
    diagnostic: string; // e.g. "8/8"
    guided: string;
    independent: string;
  };
  validation: ValidationState;
  status: LifecycleStatus;
  updated_at: string; // ISO
  updated_by: string;
  blocking_errors: number;
  warnings: number;
}

export interface DashboardStats {
  topics: number;
  micro_skills: number;
  diagnostic_questions: number;
  guided_questions: number;
  independent_questions: number;
  misconceptions: number;
  scaffolds: number;
  blocking_errors: number;
  warnings: number;
}

// ── Topic workspace hierarchy (§3, §5) ────────────────────────────────────
export type TreeNodeKind =
  | 'topic'
  | 'details'
  | 'scope-source'
  | 'micro-skills'
  | 'micro-skill'
  | 'orientation'
  | 'worked-examples'
  | 'questions'
  | 'phase'
  | 'question'
  | 'misconceptions'
  | 'misconception'
  | 'hints-cues'
  | 'scaffolds'
  | 'scaffold'
  | 'coverage'
  | 'publish'
  | 'group';

export interface TreeNode {
  id: string;
  kind: TreeNodeKind;
  label: string;
  /** Route segment under /topics/[id] this node opens, when navigable. */
  route?: string;
  /** Small count badge (children / linked assets). */
  count?: number;
  status?: LifecycleStatus | ActivityStatus;
  /** Contextual + Add action available on this node (spec §3.1). */
  addable?: boolean;
  children?: TreeNode[];
}

// ── Topic details (§6.1) ──────────────────────────────────────────────────
export interface TopicDetails {
  topic_id: string;
  topic_code: string;
  topic_title: string;
  ks_stage: KsStage;
  subject: string;
  sequence_no: number;
  learning_goal: string;
  core_message: string;
  status: ActivityStatus;
  lifecycle: LifecycleStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

// ── Micro-skill coverage counts (Topic Details "Coverage Summary" §5) ─────
export interface CoverageLine {
  label: string;
  have: number;
  need: number;
  state: CoverageState;
}

export interface MicroSkillRow {
  micro_skill_id: string;
  skill_code: string;
  skill_name: string;
  status: LifecycleStatus;
  diagnostic: number;
  worked: number;
  guided: number;
  independent: number;
  hints: number;
  updated_at: string;
}

// ── Coverage & validation grid (§14) ──────────────────────────────────────
export interface CoverageCell {
  count: number;
  state: CoverageState;
}
export interface CoverageGridRow {
  micro_skill_id: string;
  cells: Record<string, CoverageCell>; // keyed by column id
}
export interface CoverageGrid {
  columns: { id: string; label: string }[];
  rows: CoverageGridRow[];
}

export interface ValidationIssue {
  id: string;
  severity: 'blocking' | 'warning';
  message: string;
  node_route?: string;
}

// ── Full workspace payload (spec §16.1: "ready for the frontend tree") ────
export interface TopicWorkspace {
  details: TopicDetails;
  tree: TreeNode;
  coverage_summary: CoverageLine[];
  micro_skills: MicroSkillRow[];
  validation: ValidationIssue[];
}

// ── Section content (§6–§15) ──────────────────────────────────────────────
export interface ScopeItem {
  scope_item_id: string;
  scope_type: 'INCLUDED' | 'EXCLUDED';
  item_text: string;
  active: boolean;
}
export interface SourceProvenance {
  source_type: string;
  source_name: string;
  license_name: string;
  adapted: boolean;
  direct_text_copied: boolean;
  review_status: 'PENDING_FINAL_REVIEW' | 'APPROVED';
}

export interface MicroSkillDetail extends MicroSkillRow {
  description: string;
  prerequisite?: string;
  assessment_priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface OrientationScene {
  scene_no: number;
  scene_title: string;
  duration_sec: number;
  visual_action: string;
  narration_text: string;
  on_screen_text?: string;
}
export interface OrientationVideo {
  video_title: string;
  duration_sec: number;
  status: LifecycleStatus;
  scenes: OrientationScene[];
}
export interface SupportCard {
  support_card_id: string;
  card_title: string;
  visual_content: string;
  narration_or_text: string;
  status: LifecycleStatus;
}

export interface WorkedStep {
  step_no: number;
  screen_content: string;
  narration_text: string;
  must_show?: string;
  must_not_show?: string;
}
export interface SkillMapping {
  micro_skill_id: string;
  weight: number;
  is_primary: boolean;
}
export interface WorkedExample {
  worked_example_id: string;
  title: string;
  problem_statement: string;
  final_answer: string;
  status: LifecycleStatus;
  steps: WorkedStep[];
  skill_mappings: SkillMapping[];
}

export type QuestionType =
  | 'SINGLE_CHOICE'
  | 'SHORT_RESPONSE'
  | 'MULTI_PART_SHORT_RESPONSE'
  | 'CHOICE_WITH_EXPLANATION'
  | 'TRUE_FALSE_WITH_EXPLANATION';
export type Phase = 'PHASE_0_DIAGNOSTIC' | 'PHASE_2_GUIDED_LEARNING' | 'PHASE_3_INDEPENDENT_PRACTICE';

export interface Question {
  question_id: string;
  question_text: string;
  question_type: QuestionType;
  difficulty: 1 | 2;
  item_family_id: string;
  phase: Phase;
  question_role: string;
  status: LifecycleStatus;
  skill_mappings: SkillMapping[];
  canonical_answer: string;
  verification_method: string;
}

export interface ErrorType {
  error_code: string;
  error_name: string;
  description: string;
  severity: 'MEDIUM' | 'HIGH';
  detection_method: string;
  active: boolean;
}
export interface Misconception {
  misconception_id: string;
  name: string;
  description: string;
  diagnosis_rule: string;
  active: boolean;
  error_links: string[];
  skill_links: { micro_skill_id: string; relationship_type: 'DIRECT_FAILURE' | 'UNDERLYING_GAP' | 'AFFECTED_SKILL' }[];
}

export interface Hint {
  hint_id: string;
  hint_level: number;
  hint_type: 'ATTENTION' | 'CONCEPT_REMINDER' | 'PARTIAL_STEP';
  content: string;
  active: boolean;
}
export interface VisualCue {
  visual_cue_id: string;
  cue_name: string;
  cue_purpose: string;
  retrieval_keywords: string[];
  embedding_status: string;
  review_status: string;
  status: LifecycleStatus;
}

export interface ScaffoldStep {
  stage_no: number;
  prompt: string;
  expected_response: string;
  next_on_correct: string;
  next_on_incorrect: string;
}
export interface Scaffold {
  scaffold_id: string;
  scaffold_name: string;
  trigger_rule: string;
  completion_rule: string;
  active: boolean;
  steps: ScaffoldStep[];
}
export interface ParallelExample {
  parallel_example_id: string;
  misconception_id: string;
  problem_statement: string;
  final_answer: string;
  active: boolean;
}

/** Everything below the topic, fetched once for the workspace session. */
export interface TopicContent {
  scope: ScopeItem[];
  source: SourceProvenance;
  micro_skills: MicroSkillDetail[];
  orientation_video: OrientationVideo;
  support_cards: SupportCard[];
  worked_examples: WorkedExample[];
  questions: Question[];
  error_types: ErrorType[];
  misconceptions: Misconception[];
  hints: Hint[];
  visual_cues: VisualCue[];
  scaffolds: Scaffold[];
  parallel_examples: ParallelExample[];
}

// ── Global / cross-topic libraries (top-level nav) ────────────────────────
/** A library row carries its owning topic so global tables can group/link. */
export interface TopicRef {
  topic_id: string;
  topic_code: string;
}
export type LibMicroSkill = MicroSkillDetail & TopicRef;
export type LibQuestion = Question & TopicRef;
export type LibHint = Hint & TopicRef;
export type LibMisconception = Misconception & TopicRef;
export type LibVisualCue = VisualCue & TopicRef;
export type LibScaffold = Scaffold & TopicRef;

export interface GlobalLibrary {
  micro_skills: LibMicroSkill[];
  questions: LibQuestion[];
  hints: LibHint[];
  misconceptions: LibMisconception[];
  visual_cues: LibVisualCue[];
  scaffolds: LibScaffold[];
  error_types: ErrorType[];
}

/** Curriculum tree for the explorer (KS stage → subject → topic → micro-skill). */
export interface CurriculumNode {
  id: string;
  label: string;
  kind: 'stage' | 'subject' | 'topic' | 'micro-skill';
  status?: LifecycleStatus;
  topic_id?: string;
  children?: CurriculumNode[];
}

export interface ReviewItem {
  topic_id: string;
  topic_code: string;
  topic_title: string;
  ks_stage: KsStage;
  submitted_by: string;
  submitted_at: string;
  status: LifecycleStatus;
  blocking_errors: number;
  warnings: number;
  changed: string; // e.g. "12 questions, 3 micro-skills"
}

export interface ReferenceSet {
  label: string;
  description: string;
  values: string[];
}
export interface SettingsData {
  reference_sets: ReferenceSet[];
}

// ── Adapter surface ───────────────────────────────────────────────────────
export interface AuthoringApi {
  listTopics(): Promise<TopicSummary[]>;
  dashboardStats(): Promise<DashboardStats>;
  getWorkspace(topicId: string): Promise<TopicWorkspace>;
  getContent(topicId: string): Promise<TopicContent>;
  getLibrary(): Promise<GlobalLibrary>;
  getCurriculum(): Promise<CurriculumNode[]>;
  getReviewQueue(): Promise<ReviewItem[]>;
  getSettings(): Promise<SettingsData>;
  getCoverageGrid(topicId: string): Promise<CoverageGrid>;
  validateTopic(topicId: string): Promise<ValidationIssue[]>;
}
