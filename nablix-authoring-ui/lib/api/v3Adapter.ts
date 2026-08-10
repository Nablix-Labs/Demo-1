/**
 * v3 adapters. The mock serves the sample responses shipped with the contract
 * (lib/api/v3/t02-allpages-v3.json) so the portal runs on exactly the payloads
 * the backend has agreed to send; the http adapter calls the real endpoints and
 * unwraps the { success, _meta, data } envelope.
 *
 * Switch with NEXT_PUBLIC_API_MODE=http.
 */
import sample from './v3/t02-allpages-v3.json';
import type {
  AuthoringApiV3,
  CoverageData,
  DashboardData,
  HintsVisualCuesData,
  MicroSkillsData,
  MisconceptionsData,
  OrientationData,
  PageResponse,
  Phase,
  PreviewPublishData,
  QuestionsData,
  ReviewQueueData,
  ScaffoldsData,
  ScopeSourceData,
  TopicDetailsData,
  WorkedExamplesData,
} from './v3-contracts';

const PAGES = (sample as { page_samples: Record<string, PageResponse<unknown>> }).page_samples;

const QUESTION_PAGE: Record<Phase, string> = {
  PHASE_0_DIAGNOSTIC: '08_questions_diagnostic',
  PHASE_2_GUIDED_LEARNING: '09_questions_guided',
  PHASE_3_INDEPENDENT_PRACTICE: '10_questions_independent',
};

/** Reads one page out of the bundled sample. */
function page<T>(key: string): Promise<T> {
  const res = PAGES[key];
  if (!res) return Promise.reject(new Error(`No v3 sample for page "${key}"`));
  return Promise.resolve(res.data as T);
}

/**
 * The sample covers one topic (T02). Any other topic id would silently render
 * T02's content, which is worse than an error while the backend is unbuilt.
 */
export const SAMPLE_TOPIC_ID = 'ALG-ORI-02';

export const mockApiV3: AuthoringApiV3 = {
  getDashboard: () => page<DashboardData>('01_dashboard'),
  getReviewQueue: () => page<ReviewQueueData>('02_review_queue'),
  getTopicDetails: () => page<TopicDetailsData>('03_topic_details'),
  getScopeSource: () => page<ScopeSourceData>('04_scope_source'),
  getMicroSkills: () => page<MicroSkillsData>('05_micro_skills'),
  getOrientation: () => page<OrientationData>('06_orientation'),
  getWorkedExamples: () => page<WorkedExamplesData>('07_worked_examples'),
  getQuestions: (_topicId, phase) => page<QuestionsData>(QUESTION_PAGE[phase]),
  getMisconceptions: () => page<MisconceptionsData>('11_misconceptions'),
  getSupportAssets: () => page<HintsVisualCuesData>('12_hints_visual_cues'),
  getScaffolds: () => page<ScaffoldsData>('13_scaffolds_parallel_examples'),
  getCoverage: () => page<CoverageData>('14_coverage_validation'),
  getPreviewPublish: () => page<PreviewPublishData>('15_preview_publish'),
};

/** Endpoint paths are the `suggested_endpoint` values from the contract. */
export function createHttpApiV3(base: string): AuthoringApiV3 {
  const get = async <T>(path: string): Promise<T> => {
    const res = await fetch(`${base}${path}`, { headers: { Accept: 'application/json' } });
    if (!res.ok) {
      throw new Error(`Authoring API ${path} failed: ${res.status} ${res.statusText}`);
    }
    const body = (await res.json()) as PageResponse<T>;
    if (!body.success) {
      throw new Error(`Authoring API ${path} returned success=false`);
    }
    return body.data;
  };

  const topic = (id: string, section: string) => `/topics/${encodeURIComponent(id)}/${section}`;

  return {
    getDashboard: () => get<DashboardData>('/topics'),
    getReviewQueue: () => get<ReviewQueueData>('/review-queue'),
    getTopicDetails: (id) => get<TopicDetailsData>(topic(id, 'workspace')),
    getScopeSource: (id) => get<ScopeSourceData>(topic(id, 'scope-source')),
    getMicroSkills: (id) => get<MicroSkillsData>(topic(id, 'micro-skills')),
    getOrientation: (id) => get<OrientationData>(topic(id, 'orientation')),
    getWorkedExamples: (id) => get<WorkedExamplesData>(topic(id, 'worked-examples')),
    getQuestions: (id, phase) => get<QuestionsData>(`${topic(id, 'questions')}?phase=${phase}`),
    getMisconceptions: (id) => get<MisconceptionsData>(topic(id, 'misconceptions')),
    getSupportAssets: (id) => get<HintsVisualCuesData>(topic(id, 'support-assets')),
    getScaffolds: (id) => get<ScaffoldsData>(topic(id, 'scaffolds-parallel-examples')),
    getCoverage: (id) => get<CoverageData>(topic(id, 'coverage')),
    getPreviewPublish: (id) => get<PreviewPublishData>(topic(id, 'preview-publish')),
  };
}

const mode = process.env.NEXT_PUBLIC_API_MODE ?? 'mock';

export const apiV3: AuthoringApiV3 =
  mode === 'http'
    ? createHttpApiV3(process.env.NEXT_PUBLIC_AUTHORING_API_BASE ?? '/authoring')
    : mockApiV3;
