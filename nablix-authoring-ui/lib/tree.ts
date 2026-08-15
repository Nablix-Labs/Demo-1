/**
 * The workspace tree is a product construct, not an API payload — v3 returns
 * counts and health per page, never a tree. Its shape is fixed by spec §3; the
 * only thing that varies is the counts beside each node.
 *
 * Also holds the page_id → route map used to turn a validation issue's
 * navigate_to metadata into a link (guide §3.2), so no page hard-codes routes.
 */
import type { HealthState, NavigateTo, TopicDetailsData, ValidationIssue } from './api/v3-contracts';

export type TreeNodeKind =
  | 'topic'
  | 'details'
  | 'scope-source'
  | 'micro-skills'
  | 'orientation'
  | 'worked-examples'
  | 'questions'
  | 'phase'
  | 'misconceptions'
  | 'hints-cues'
  | 'scaffolds'
  | 'coverage'
  | 'publish';

export interface TreeNode {
  id: string;
  kind: TreeNodeKind;
  label: string;
  route?: string;
  count?: number;
  addable?: boolean;
  /** Rolled up from the validation issues that point at this node's page. */
  health?: HealthState;
  children?: TreeNode[];
}

/**
 * Roll each validation issue up to the tree node whose page it belongs to
 * (guide §2.3): one blocking issue makes the node MISSING, otherwise any issue
 * makes it WARNING. The states themselves are the backend's; this only decides
 * which node shows them.
 */
export function healthByRoute(issues: ValidationIssue[]): Record<string, HealthState> {
  const out: Record<string, HealthState> = {};
  for (const issue of issues) {
    const route = routeForPage(issue.navigate_to?.page_id);
    if (!route) continue;
    if (issue.blocking) out[route] = 'MISSING';
    else if (out[route] !== 'MISSING') out[route] = 'WARNING';
  }
  return out;
}

type Counts = TopicDetailsData['hierarchy_counts'];

export function buildTopicTree(counts?: Counts, health: Record<string, HealthState> = {}): TreeNode {
  return {
    id: 'topic',
    kind: 'topic',
    label: 'Topic',
    children: ([
      { id: 'details', kind: 'details', label: 'Topic Details', route: 'details' },
      { id: 'scope-source', kind: 'scope-source', label: 'Scope & Source', route: 'scope-source' },
      {
        id: 'micro-skills',
        kind: 'micro-skills',
        label: 'Micro-skills',
        route: 'micro-skills',
        count: counts?.micro_skills,
        addable: true,
      },
      { id: 'orientation', kind: 'orientation', label: 'Orientation', route: 'orientation', addable: true },
      { id: 'worked-examples', kind: 'worked-examples', label: 'Worked Examples', route: 'worked-examples', addable: true },
      {
        id: 'questions',
        kind: 'questions',
        label: 'Questions',
        route: 'questions',
        count: counts?.questions,
        addable: true,
      },
      {
        id: 'misconceptions',
        kind: 'misconceptions',
        label: 'Misconceptions',
        route: 'misconceptions',
        count: counts?.misconceptions,
        addable: true,
      },
      {
        id: 'hints-cues',
        kind: 'hints-cues',
        label: 'Hints & Visual Cues',
        route: 'hints-cues',
        count: (counts?.hints ?? 0) + (counts?.visual_cues ?? 0) || undefined,
        addable: true,
      },
      {
        id: 'scaffolds',
        kind: 'scaffolds',
        label: 'Scaffolds & Parallel',
        route: 'scaffolds',
        count: counts?.scaffolds,
        addable: true,
      },
      { id: 'coverage', kind: 'coverage', label: 'Coverage & Validation', route: 'coverage' },
      { id: 'publish', kind: 'publish', label: 'Preview & Publish', route: 'publish' },
    ] as TreeNode[]).map((node) =>
      node.route && health[node.route] ? { ...node, health: health[node.route] } : node,
    ),
  };
}

const PAGE_ROUTE: Record<string, string> = {
  TOPIC_DETAILS: 'details',
  SCOPE_SOURCE: 'scope-source',
  MICRO_SKILLS: 'micro-skills',
  ORIENTATION: 'orientation',
  WORKED_EXAMPLES: 'worked-examples',
  QUESTIONS: 'questions',
  '08_QUESTIONS_DIAGNOSTIC': 'questions',
  '09_QUESTIONS_GUIDED': 'questions',
  '10_QUESTIONS_INDEPENDENT': 'questions',
  MISCONCEPTIONS: 'misconceptions',
  HINTS_VISUAL_CUES: 'hints-cues',
  SCAFFOLDS_PARALLEL: 'scaffolds',
  COVERAGE_VALIDATION: 'coverage',
  PREVIEW_PUBLISH: 'publish',
};

/** Route for an issue's navigate_to, or undefined when the page is unknown. */
export function routeForPage(pageId?: string): string | undefined {
  return pageId ? PAGE_ROUTE[pageId] : undefined;
}

const PAGE_PHASE: Record<string, string> = {
  '08_QUESTIONS_DIAGNOSTIC': 'PHASE_0_DIAGNOSTIC',
  '09_QUESTIONS_GUIDED': 'PHASE_2_GUIDED_LEARNING',
  '10_QUESTIONS_INDEPENDENT': 'PHASE_3_INDEPENDENT_PRACTICE',
};

/** navigate_to carries page_id, an optional tab_id, and one record key. */
function recordIdOf(nav: NavigateTo): string | undefined {
  for (const [k, v] of Object.entries(nav)) {
    if (k !== 'page_id' && k !== 'tab_id' && typeof v === 'string') return v;
  }
  return undefined;
}

/**
 * Turn an issue's navigate_to into a link that opens the affected record, not
 * just its page (guide §3.2). The target page reads `select`/`tab`/`phase` and
 * treats them as an override of its own default_selection.
 */
export function linkForIssue(topicId: string, issue: { navigate_to?: NavigateTo }): string | undefined {
  const nav = issue.navigate_to;
  const route = routeForPage(nav?.page_id);
  if (!nav || !route) return undefined;
  const qs = new URLSearchParams();
  const id = recordIdOf(nav);
  if (id) qs.set('select', id);
  if (nav.tab_id) qs.set('tab', nav.tab_id);
  const phase = PAGE_PHASE[nav.page_id];
  if (phase) qs.set('phase', phase);
  const q = qs.toString();
  return `/topics/${topicId}/${route}${q ? `?${q}` : ''}`;
}

/**
 * Where a coverage cell leads. The guide wants a click to open the creation
 * flow with topic and micro-skill prefilled, but v3 sends no `add_action` on
 * coverage cells, so this goes as far as the data allows: the owning section,
 * and the phase when the column names one.
 */
const COVERAGE_TARGET: Record<string, { route: string; phase?: string }> = {
  diagnostic: { route: 'questions', phase: 'PHASE_0_DIAGNOSTIC' },
  guided: { route: 'questions', phase: 'PHASE_2_GUIDED_LEARNING' },
  independent: { route: 'questions', phase: 'PHASE_3_INDEPENDENT_PRACTICE' },
  worked_example: { route: 'worked-examples' },
  misconceptions: { route: 'misconceptions' },
  hints: { route: 'hints-cues' },
  visual_cues: { route: 'hints-cues' },
  scaffolds: { route: 'scaffolds' },
  parallel_examples: { route: 'scaffolds' },
};

export function linkForCoverageCell(topicId: string, column: string): string | undefined {
  const target = COVERAGE_TARGET[column];
  if (!target) return undefined;
  const q = target.phase ? `?phase=${target.phase}` : '';
  return `/topics/${topicId}/${target.route}${q}`;
}
