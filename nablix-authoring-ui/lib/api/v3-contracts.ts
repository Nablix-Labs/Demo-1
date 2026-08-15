/**
 * UI Hierarchy Contract v3.0-hierarchical — TypeScript mirror of the fifteen
 * page responses in Nablix_Content_Approver_T02_UI_Hierarchy_AllPages_v3.json.
 *
 * These types describe what the backend sends, verbatim. Where v3 is internally
 * inconsistent (see TopicRef vs TopicDetails below) the inconsistency is
 * modelled rather than smoothed over, so the mismatch stays visible until the
 * backend settles it — see docs/contract/V3-RECONCILIATION.md.
 *
 * IDs, ordering and health are all backend-resolved. The UI never mints an ID,
 * never sorts by a field the API didn't order, and never computes health.
 */

// ── Envelope (guide §1.2) ─────────────────────────────────────────────────
export interface PageMeta {
  page_id: string;
  page_name: string;
  suggested_endpoint: string;
  sample_topic_id: string;
  sample_topic_code: string;
  ui_contract_version: string;
  source: string;
}

export interface PageResponse<T> {
  success: boolean;
  _meta: PageMeta;
  data: T;
}

// ── Health (guide §3) ─────────────────────────────────────────────────────
export type HealthState = 'COMPLETE' | 'WARNING' | 'MISSING';
export type HealthIndicator = 'GREEN_CHECK' | 'AMBER_WARNING' | 'RED_X';

export interface HealthIssue {
  code: string;
  severity: 'ERROR' | 'WARNING';
  message: string;
}

export interface AddAction {
  action: string;
  prefill?: Record<string, string>;
}

export interface ContentHealth {
  state: HealthState;
  indicator: HealthIndicator;
  blocking: boolean;
  issues?: HealthIssue[];
  add_action?: AddAction;
}

/** Navigation metadata on a validation issue (guide §3.2). */
export interface NavigateTo {
  page_id: string;
  tab_id?: string;
  [recordKey: string]: string | undefined;
}

export interface ValidationIssue {
  code: string;
  severity: 'ERROR' | 'WARNING';
  record_type: string;
  record_id: string;
  message: string;
  blocking: boolean;
  navigate_to?: NavigateTo;
}

// ── Shared value objects ──────────────────────────────────────────────────
export type KsStage = 'KS3' | 'KS4';
export type WorkflowStatus = 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'PUBLISHED' | 'ARCHIVED';
export type ActivityStatus = 'ACTIVE' | 'INACTIVE';
export type Phase =
  | 'PHASE_0_DIAGNOSTIC'
  | 'PHASE_1_ORIENTATION'
  | 'PHASE_2_GUIDED_LEARNING'
  | 'PHASE_3_INDEPENDENT_PRACTICE';

/** Only these three are authored as question phases; orientation has no questions. */
export type QuestionPhase = Exclude<Phase, 'PHASE_1_ORIENTATION'>;

/** Topic stub on every workspace page. Note: `title`, not `topic_title`. */
export interface TopicRef {
  topic_id: string;
  topic_code: string;
  title: string;
  ks_stage: KsStage;
}

export interface MicroSkill {
  micro_skill_id: string;
  skill_code: string;
  skill_name: string;
  description: string;
  assessment_priority: 'HIGH' | 'MEDIUM' | 'LOW';
  status: ActivityStatus;
  version: string;
}

export interface ErrorType {
  error_code: string;
  error_name: string;
  description: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  detection_method: string;
  active: boolean;
}

export interface MisconceptionRef {
  misconception_id: string;
  name: string;
  description: string;
  active: boolean;
  version: string;
}

export interface QuestionRef {
  question_id: string;
  question_text: string;
  question_type: string;
  difficulty: number;
  phase: Phase;
  question_role: string;
}

// ── 01 Dashboard ──────────────────────────────────────────────────────────
export interface TopicValidation {
  state: HealthState;
  indicator: HealthIndicator;
  blocking_count: number;
  warning_count: number;
}

export interface DashboardTopicRow {
  topic_id: string;
  topic_code: string;
  title: string;
  ks_stage: KsStage;
  completion_percent: number;
  coverage: { diagnostic: string; guided: string; independent: string };
  validation: TopicValidation;
  workflow_status: WorkflowStatus;
  updated_at: string;
}

export interface DashboardData {
  summary: {
    micro_skills: number;
    diagnostic_questions: number;
    guided_questions: number;
    independent_questions: number;
    misconceptions: number;
    scaffolds: number;
  };
  topics: DashboardTopicRow[];
  ui_rule: string;
}

// ── 02 Review queue ───────────────────────────────────────────────────────
export interface ReviewQueueItem {
  topic_id: string;
  topic_code: string;
  title: string;
  ks_stage: KsStage;
  workflow_status: WorkflowStatus;
  validation: { blocking_count: number; warning_count: number; state: HealthState };
  default_action: string;
}

export interface ReviewQueueData {
  items: ReviewQueueItem[];
}

// ── 03 Topic details ──────────────────────────────────────────────────────
/** The one page where v3 sends `topic_title` rather than `title`. */
export interface TopicDetails {
  topic_id: string;
  topic_code: string;
  topic_title: string;
  ks_stage: KsStage;
  sequence_no: number;
  learning_goal: string;
  core_message: string;
  status: string;
  version: string;
  created_at: string;
  updated_at: string;
}

export interface TopicDetailsData {
  topic: TopicDetails;
  hierarchy_counts: {
    micro_skills: number;
    questions: number;
    misconceptions: number;
    hints: number;
    visual_cues: number;
    scaffolds: number;
  };
  selection: { selected_node_type: string; selected_node_id: string };
  content_health: ContentHealth;
}

// ── 04 Scope & source ─────────────────────────────────────────────────────
export interface ScopeGroup {
  group_id: string;
  label: string;
  items: Record<string, unknown>[];
  content_health?: ContentHealth;
}

export interface ScopeSourceData {
  topic: TopicRef;
  hierarchy: { groups: ScopeGroup[] };
  default_selection: { group_id: string; item_id: string };
  content_health: ContentHealth;
}

// ── 05 Micro-skills ───────────────────────────────────────────────────────
export interface MicroSkillNode {
  micro_skill_id: string;
  display_order: number;
  label: string;
  content_health: ContentHealth;
  coverage_counts: Record<string, number>;
}

export interface MicroSkillsData {
  topic: TopicRef;
  hierarchy: { micro_skills: MicroSkillNode[] };
  default_selection: { micro_skill_id: string };
  selected_item: {
    entity_type: string;
    details: MicroSkill;
    linked_questions: QuestionRef[];
    linked_misconceptions: MisconceptionRef[];
  };
  selection_rule: string;
}

// ── 06 Orientation ────────────────────────────────────────────────────────
export interface OrientationScene {
  scene_id: string;
  video_id: string;
  scene_no: number;
  scene_title: string;
  duration_sec: number;
  visual_action: string;
  narration_text: string;
  on_screen_text?: string;
  direction?: string;
  status: string;
}

export interface SupportCard {
  support_card_id: string;
  topic_id: string;
  card_title: string;
  visual_content: string;
  narration_or_text: string;
  restriction: string;
  status: string;
  version: string;
}

export interface OrientationData {
  topic: TopicRef;
  hierarchy: {
    video: {
      video_id: string;
      label: string;
      children: { scenes: OrientationScene[] };
      content_health: ContentHealth;
    };
    support_cards: SupportCard[];
  };
  default_selection: { node_type: string; node_id: string };
}

// ── 07 Worked examples ────────────────────────────────────────────────────
export interface WorkedStep {
  worked_example_step_id: string;
  worked_example_id: string;
  step_no: number;
  screen_content: string;
  narration_text: string;
  must_show?: string;
  must_not_show?: string;
}

export interface SkillMapping {
  micro_skill_id: string;
  skill_name: string;
  weight: number;
  is_primary: boolean;
  worked_example_id?: string;
}

export interface WorkedExampleNode {
  worked_example_id: string;
  label: string;
  details: {
    worked_example_id: string;
    topic_id: string;
    title: string;
    phase: string;
    problem_statement: string;
    final_answer: string;
    status: string;
    version: string;
  };
  children: { steps: WorkedStep[]; micro_skill_mappings: SkillMapping[] };
  content_health: ContentHealth;
}

export interface WorkedExamplesData {
  topic: TopicRef;
  hierarchy: { worked_examples: WorkedExampleNode[] };
  default_selection: { worked_example_id: string };
  selected_item: WorkedExampleNode;
  selection_rule: string;
}

// ── 08/09/10 Questions (one shape, three phases) ──────────────────────────
export interface QuestionNode {
  question_id: string;
  sequence_order: number;
  label: string;
  question_type: string;
  difficulty: number;
  question_role: string;
  content_health: ContentHealth;
  child_counts: {
    usage: number;
    micro_skill_mappings: number;
    answer_specification: number;
    error_mappings: number;
  };
}

export interface QuestionUsage {
  question_usage_id: string;
  question_id: string;
  phase: Phase;
  question_role: string;
  sequence_order: number;
  support_allowed: string;
  max_attempts: number;
  active: boolean;
}

/** The canvas answer walkthrough — this is the workbook's `answer_steps`. */
export interface AnswerStep {
  step_no: number;
  text: string;
}

export interface AnswerSpecification {
  answer_spec_id: string;
  answer_type: string;
  canonical_answer: string;
  accepted_answers: string[];
  common_wrong_answers: string[];
  verification_method: string;
  required_units: string | null;
  explanation_required: boolean;
  answer_steps: AnswerStep[];
}

export interface ErrorMapping {
  response_pattern: string;
  error: ErrorType;
  /** Null until Question_Error_Map.micro_skill_id ships — reconciliation §1.2. */
  micro_skill_id: string | null;
  micro_skill_context_source?: string;
  source_schema_has_micro_skill_id?: boolean;
}

export interface QuestionPackage {
  entity_type: string;
  question: {
    question_id: string;
    question_text: string;
    question_type: string;
    difficulty: number;
    item_family_id: string;
    source_provenance_id: string;
    status: string;
    version: string;
  };
  children: {
    usage: QuestionUsage | null;
    micro_skill_mappings: SkillMapping[];
    answer_specification: AnswerSpecification | null;
    error_mappings: ErrorMapping[];
  };
}

export interface QuestionsData {
  topic: TopicRef;
  phase: { phase_id: QuestionPhase; label: string };
  hierarchy: { questions: QuestionNode[] };
  default_selection: { question_id: string };
  selected_item: QuestionPackage;
  selection_rule: string;
}

// ── 11 Misconceptions ─────────────────────────────────────────────────────
export interface SupportChild {
  hint_id?: string;
  visual_cue_id?: string;
  sequence_order: number;
  label: string;
  preview: string;
  active: boolean;
  shared_by_misconception_count?: number;
  shared_by_misconception_ids?: string[];
  content_health: ContentHealth;
}

export interface MisconceptionChildren {
  linked_errors: { error_code: string; confidence_weight: number; label: string }[];
  linked_micro_skills: { micro_skill_id: string; relationship_type: string; label: string }[];
  hints: SupportChild[];
  visual_cues: SupportChild[];
  parallel_examples: {
    parallel_example_id: string;
    label: string;
    active: boolean;
    content_health: ContentHealth;
  }[];
}

export interface MisconceptionNode {
  misconception_id: string;
  display_order: number;
  label: string;
  content_health: ContentHealth;
  child_counts: Record<string, number>;
  children: MisconceptionChildren;
}

export interface MisconceptionsData {
  topic: TopicRef;
  hierarchy: { misconceptions: MisconceptionNode[] };
  default_selection: { misconception_id: string };
  selected_item: {
    entity_type: string;
    details: MisconceptionRef & { diagnosis_rule?: string };
    children: MisconceptionChildren;
    affected_questions: QuestionRef[];
  };
  selection_rule: string;
}

// ── 12 Hints & visual cues ────────────────────────────────────────────────
/** Careful: the tab ids are plural, the support types are singular. */
export type SupportType = 'HINT' | 'VISUAL_CUE';
export type SupportTabId = 'HINTS' | 'VISUAL_CUES';

export const TAB_FOR_SUPPORT: Record<SupportType, SupportTabId> = {
  HINT: 'HINTS',
  VISUAL_CUE: 'VISUAL_CUES',
};

export interface MisconceptionGroup {
  misconception_id: string;
  display_order: number;
  label: string;
  content_health: ContentHealth;
  hints: SupportChild[];
  visual_cues: SupportChild[];
}

export interface SupportImpactContext {
  linked_misconceptions: MisconceptionRef[];
  related_micro_skills: MicroSkill[];
  linked_errors: ErrorType[];
  affected_questions: QuestionRef[];
  sibling_visual_cues?: SupportChild[];
  sibling_hints?: SupportChild[];
  parallel_examples?: { parallel_example_id: string; problem_statement: string; final_answer: string }[];
}

export interface SelectedSupportItem {
  entity_type: SupportType;
  hint_id?: string;
  hint_level?: number;
  hint_type?: string;
  visual_cue_id?: string;
  cue_name?: string;
  cue_purpose?: string;
  content?: string;
  active: boolean;
  parent_context: { selected_misconception: MisconceptionRef; sequence_order: number };
  impact_context: SupportImpactContext;
  edit_rule?: { content_only_change: string; relationship_change: string };
}

export interface HintsVisualCuesData {
  topic: TopicRef;
  tabs: { tab_id: SupportTabId; label: string }[];
  active_tab: SupportTabId;
  hierarchy: { misconception_groups: MisconceptionGroup[] };
  default_selection: {
    misconception_id: string;
    support_type: SupportType;
    support_id: string;
    reason: string;
  };
  selected_context: {
    misconception: MisconceptionRef;
    linked_errors: ErrorType[];
    linked_micro_skills: MicroSkill[];
  };
  selected_item: SelectedSupportItem;
  interaction_rules: Record<string, string | string[]>;
  missing_content_display: Record<string, { indicator: string; label: string; blocks_submit_or_publish: boolean }>;
}

// ── 13 Scaffolds & parallel examples ──────────────────────────────────────
export interface ScaffoldStep {
  scaffold_step_id: string;
  scaffold_id: string;
  stage_no: number;
  prompt: string;
  partial_content?: string;
  expected_response: string;
  next_on_correct: string;
  next_on_incorrect: string;
}

export interface QuestionLink {
  question_id: string;
  question_text: string;
  micro_skill_id: string;
  micro_skill_name: string;
  priority: number;
}

export interface ScaffoldNode {
  scaffold_id: string;
  label: string;
  details: {
    scaffold_id: string;
    scaffold_name: string;
    trigger_rule: string;
    completion_rule: string;
    active: boolean;
  };
  children: { steps: ScaffoldStep[]; question_links: QuestionLink[] };
  content_health: ContentHealth;
}

export interface ParallelExampleGroup {
  misconception_id: string;
  label: string;
  items: Record<string, unknown>[];
}

export interface ScaffoldsData {
  topic: TopicRef;
  tabs: { tab_id: string; label: string }[];
  active_tab: string;
  hierarchy: {
    scaffolds: ScaffoldNode[];
    parallel_examples_by_misconception: ParallelExampleGroup[];
  };
  default_selection: { tab_id: string; scaffold_id: string };
  selected_item: ScaffoldNode;
}

// ── 14 Coverage & validation ──────────────────────────────────────────────
export interface CoverageCell {
  count: number;
  required_min: number;
  content_health: ContentHealth;
}

export interface CoverageRow {
  micro_skill_id: string;
  skill_name: string;
  cells: Record<string, CoverageCell>;
}

export interface CoverageData {
  topic: TopicRef;
  coverage_rows: CoverageRow[];
  validation_summary: {
    blocking_count: number;
    warning_count: number;
    issues: ValidationIssue[];
  };
  display_rule: Record<string, string>;
}

// ── 15 Preview, review & publish ──────────────────────────────────────────
export interface LearnerFlowSection {
  sequence: number;
  section: string;
  count: number;
  content_health: ContentHealth;
}

export interface PreviewPublishData {
  topic: TopicRef;
  learner_flow_sections: LearnerFlowSection[];
  workflow: {
    current_status: WorkflowStatus;
    available_actions: string[];
    publish_allowed: boolean;
    publish_block_reason: string;
  };
}

// ── Adapter surface — one method per v3 page ──────────────────────────────
export interface AuthoringApiV3 {
  getDashboard(): Promise<DashboardData>;
  getReviewQueue(): Promise<ReviewQueueData>;
  getTopicDetails(topicId: string): Promise<TopicDetailsData>;
  getScopeSource(topicId: string): Promise<ScopeSourceData>;
  getMicroSkills(topicId: string): Promise<MicroSkillsData>;
  getOrientation(topicId: string): Promise<OrientationData>;
  getWorkedExamples(topicId: string): Promise<WorkedExamplesData>;
  getQuestions(topicId: string, phase: QuestionPhase): Promise<QuestionsData>;
  getMisconceptions(topicId: string): Promise<MisconceptionsData>;
  getSupportAssets(topicId: string): Promise<HintsVisualCuesData>;
  getScaffolds(topicId: string): Promise<ScaffoldsData>;
  getCoverage(topicId: string): Promise<CoverageData>;
  getPreviewPublish(topicId: string): Promise<PreviewPublishData>;
}
