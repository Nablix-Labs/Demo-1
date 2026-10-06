/**
 * Cross-topic library loaders for the top-level library screens.
 *
 * The authoring API has no cross-topic endpoints, so every library is built the
 * same way: the dashboard supplies the topic list, each topic's own v3 page is
 * fetched in parallel, and the hierarchy nodes are flattened into rows stamped
 * with the topic they came from. Nothing here is invented — a row carries only
 * fields the v3 page sent.
 *
 * A dashboard failure rejects (there is no topic list to work from). A single
 * topic's page failing does not: its code is reported in `failed` and the other
 * topics still render, so one bad topic never blanks the whole library.
 */
import { apiV3 } from './v3Adapter';
import type {
  DashboardTopicRow,
  KsStage,
  MicroSkillNode,
  MisconceptionNode,
  QuestionNode,
  QuestionPhase,
  ScaffoldNode,
  SupportChild,
  WorkflowStatus,
} from './v3-contracts';

/** The topic a library row belongs to, as the dashboard named it. */
export interface TopicStamp {
  topic_id: string;
  topic_code: string;
  topic_title: string;
}

export interface LibraryResult<T> {
  rows: T[];
  /** topic_codes whose page could not be loaded. */
  failed: string[];
}

function stamp(t: DashboardTopicRow): TopicStamp {
  return { topic_id: t.topic_id, topic_code: t.topic_code, topic_title: t.title };
}

async function topics(): Promise<DashboardTopicRow[]> {
  const d = await apiV3.getDashboard();
  return d?.topics ?? [];
}

/** Runs one loader per dashboard topic and concatenates the rows. */
async function eachTopic<T>(load: (t: DashboardTopicRow) => Promise<T[]>): Promise<LibraryResult<T>> {
  const list = await topics();
  const failed: string[] = [];
  const parts = await Promise.all(
    list.map((t) =>
      load(t).catch(() => {
        failed.push(t.topic_code);
        return [] as T[];
      }),
    ),
  );
  return { rows: parts.flat(), failed };
}

// ── Micro-skills ──────────────────────────────────────────────────────────
export type MicroSkillRow = MicroSkillNode & TopicStamp;

export function loadMicroSkills(): Promise<LibraryResult<MicroSkillRow>> {
  return eachTopic(async (t) => {
    const d = await apiV3.getMicroSkills(t.topic_id);
    return (d?.hierarchy?.micro_skills ?? []).map((m) => ({ ...m, ...stamp(t) }));
  });
}

// ── Questions ─────────────────────────────────────────────────────────────
export const QUESTION_PHASES: { id: QuestionPhase; label: string }[] = [
  { id: 'PHASE_0_DIAGNOSTIC', label: 'Phase 0' },
  { id: 'PHASE_2_GUIDED_LEARNING', label: 'Phase 2' },
  { id: 'PHASE_3_INDEPENDENT_PRACTICE', label: 'Phase 3' },
];

export type QuestionRow = QuestionNode & TopicStamp & { phase_id: QuestionPhase; phase_label: string };

export function loadQuestions(): Promise<LibraryResult<QuestionRow>> {
  return eachTopic(async (t) => {
    const pages = await Promise.all(QUESTION_PHASES.map((p) => apiV3.getQuestions(t.topic_id, p.id)));
    return pages.flatMap((d, i) => {
      const phase = QUESTION_PHASES[i];
      return (d?.hierarchy?.questions ?? []).map((q) => ({
        ...q,
        ...stamp(t),
        phase_id: phase.id,
        phase_label: d?.phase?.label ?? phase.label,
      }));
    });
  });
}

// ── Misconceptions ────────────────────────────────────────────────────────
export type MisconceptionRow = MisconceptionNode & TopicStamp;

export function loadMisconceptions(): Promise<LibraryResult<MisconceptionRow>> {
  return eachTopic(async (t) => {
    const d = await apiV3.getMisconceptions(t.topic_id);
    return (d?.hierarchy?.misconceptions ?? []).map((m) => ({ ...m, ...stamp(t) }));
  });
}

// ── Hints & visual cues ───────────────────────────────────────────────────
/**
 * One support asset, once. The page groups assets under misconceptions and a
 * shared asset appears under each of them, so rows are deduped by id within a
 * topic and keep the labels of every group they were listed under.
 */
export type SupportRow = SupportChild & TopicStamp & { id: string; misconceptions: string[] };

function loadSupport(kind: 'hints' | 'visual_cues'): Promise<LibraryResult<SupportRow>> {
  return eachTopic(async (t) => {
    const d = await apiV3.getSupportAssets(t.topic_id);
    const byId = new Map<string, SupportRow>();
    for (const g of d?.hierarchy?.misconception_groups ?? []) {
      for (const a of g[kind] ?? []) {
        const id = (kind === 'hints' ? a.hint_id : a.visual_cue_id) ?? a.label;
        const seen = byId.get(id);
        if (seen) {
          if (!seen.misconceptions.includes(g.label)) seen.misconceptions.push(g.label);
        } else {
          byId.set(id, { ...a, ...stamp(t), id, misconceptions: [g.label] });
        }
      }
    }
    return [...byId.values()];
  });
}

export const loadHints = () => loadSupport('hints');
export const loadVisualCues = () => loadSupport('visual_cues');

// ── Scaffolds ─────────────────────────────────────────────────────────────
export type ScaffoldRow = ScaffoldNode & TopicStamp;

export function loadScaffolds(): Promise<LibraryResult<ScaffoldRow>> {
  return eachTopic(async (t) => {
    const d = await apiV3.getScaffolds(t.topic_id);
    return (d?.hierarchy?.scaffolds ?? []).map((s) => ({ ...s, ...stamp(t) }));
  });
}

// ── Curriculum ────────────────────────────────────────────────────────────
export interface CurriculumTopic {
  topic: DashboardTopicRow;
  /** Null when this topic's micro-skills page failed to load. */
  micro_skills: MicroSkillNode[] | null;
}

export interface CurriculumStage {
  ks_stage: KsStage | string;
  topics: CurriculumTopic[];
}

/** KS stage → topic → micro-skills, in the order the dashboard listed topics. */
export async function loadCurriculum(): Promise<CurriculumStage[]> {
  const list = await topics();
  const withSkills = await Promise.all(
    list.map(async (t): Promise<CurriculumTopic> => {
      try {
        const d = await apiV3.getMicroSkills(t.topic_id);
        return { topic: t, micro_skills: d?.hierarchy?.micro_skills ?? [] };
      } catch {
        return { topic: t, micro_skills: null };
      }
    }),
  );
  const stages = new Map<string, CurriculumTopic[]>();
  for (const c of withSkills) {
    const key = c.topic.ks_stage ?? 'Unstaged';
    stages.set(key, [...(stages.get(key) ?? []), c]);
  }
  return [...stages].map(([ks_stage, ts]) => ({ ks_stage, topics: ts }));
}

// ── Reference values ──────────────────────────────────────────────────────
export interface ReferenceSet {
  label: string;
  source: string;
  values: string[];
}

function distinct(values: (string | number | null | undefined)[]): string[] {
  const out = new Set<string>();
  for (const v of values) if (v !== null && v !== undefined && v !== '') out.add(String(v));
  return [...out].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

/**
 * The values actually present in live content. There is no settings or
 * vocabulary endpoint, so these are read off the data rather than an allowed
 * list — a value no record uses yet will not appear.
 */
export async function loadReferenceValues(): Promise<LibraryResult<ReferenceSet>> {
  const [list, questions] = await Promise.all([topics(), loadQuestions()]);
  const statuses: (WorkflowStatus | string)[] = list.map((t) => t.workflow_status);
  return {
    failed: questions.failed,
    rows: [
      { label: 'Question types', source: 'question_type · questions, all phases', values: distinct(questions.rows.map((q) => q.question_type)) },
      { label: 'Question roles', source: 'question_role · questions, all phases', values: distinct(questions.rows.map((q) => q.question_role)) },
      { label: 'Difficulty levels', source: 'difficulty · questions, all phases', values: distinct(questions.rows.map((q) => q.difficulty)) },
      { label: 'KS stages', source: 'ks_stage · dashboard topics', values: distinct(list.map((t) => t.ks_stage)) },
      { label: 'Workflow statuses', source: 'workflow_status · dashboard topics', values: distinct(statuses) },
    ],
  };
}
