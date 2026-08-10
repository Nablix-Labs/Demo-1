/**
 * The workspace tree is a product construct, not an API payload — v3 returns
 * counts and health per page, never a tree. Its shape is fixed by spec §3; the
 * only thing that varies is the counts beside each node.
 *
 * Also holds the page_id → route map used to turn a validation issue's
 * navigate_to metadata into a link (guide §3.2), so no page hard-codes routes.
 */
import type { TopicDetailsData } from './api/v3-contracts';

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
  children?: TreeNode[];
}

type Counts = TopicDetailsData['hierarchy_counts'];

export function buildTopicTree(counts?: Counts): TreeNode {
  return {
    id: 'topic',
    kind: 'topic',
    label: 'Topic',
    children: [
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
    ],
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
