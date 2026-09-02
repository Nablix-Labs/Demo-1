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
  QuestionPhase,
  PreviewPublishData,
  QuestionsData,
  ReviewQueueData,
  ScaffoldsData,
  ScopeSourceData,
  TopicDetailsData,
  WorkedExamplesData,
} from './v3-contracts';

const PAGES = (sample as { page_samples: Record<string, PageResponse<unknown>> }).page_samples;

const QUESTION_PAGE: Record<QuestionPhase, string> = {
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
  approveTopic: (_topicId, comment) => mockWorkflowAction('APPROVE', comment),
  returnTopic: (_topicId, comment) => mockWorkflowAction('RETURN', comment),
};

/**
 * Move the sample's workflow so the buttons visibly do something on mock data.
 *
 * The sample is a static import shared by every read, so this mutates the one
 * `15_preview_publish` payload in place — which is the point: the next
 * `getPreviewPublish` must observe the change, exactly as it would against the
 * real backend. Scoped to the workflow block; no other page is touched.
 *
 * Deliberately NOT a faithful simulation of the backend's state machine. It
 * moves the status and offers the actions that plainly follow from it, so the
 * portal is demoable without the API. The real transitions are the server's.
 */
function mockWorkflowAction(action: 'APPROVE' | 'RETURN', comment?: string): Promise<void> {
  if (action === 'RETURN' && !comment?.trim()) {
    return Promise.reject(new Error('A comment is required when returning a topic.'));
  }
  const res = PAGES['15_preview_publish'] as PageResponse<PreviewPublishData> | undefined;
  if (!res) return Promise.resolve();
  const approved = action === 'APPROVE';
  res.data.workflow = {
    ...res.data.workflow,
    current_status: approved ? 'APPROVED' : 'DRAFT',
    available_actions: approved ? ['PREVIEW', 'PUBLISH'] : ['VALIDATE', 'PREVIEW'],
    publish_allowed: approved,
    publish_block_reason: approved ? '' : 'Returned for changes; publish requires APPROVED.',
  };
  return Promise.resolve();
}

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

  /**
   * A workflow action. Unlike `get`, the reply is not read: the resulting
   * workflow state is re-fetched from the page endpoint so the server stays the
   * one deciding it.
   *
   * The server's message is preferred over the status line when it sends one —
   * role gating is enforced (a caller without the approver role gets 403
   * FORBIDDEN with an `error_code`), and "You do not have permission to access
   * this resource" tells an approver what to do about it in a way that
   * "Forbidden" does not.
   */
  const post = async (path: string, body: Record<string, string>): Promise<void> => {
    const res = await fetch(`${base}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res
        .json()
        .then((b: { message?: string; detail?: string }) => b.message ?? b.detail ?? '')
        .catch(() => '');
      throw new Error(detail || `Authoring API ${path} failed: ${res.status} ${res.statusText}`);
    }
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
    approveTopic: (id, comment) =>
      post(topic(id, 'approve'), comment?.trim() ? { comment: comment.trim() } : {}),
    returnTopic: (id, comment) => post(topic(id, 'return'), { comment: comment.trim() }),
  };
}

const mode = process.env.NEXT_PUBLIC_API_MODE ?? 'mock';

export const apiV3: AuthoringApiV3 =
  mode === 'http'
    ? createHttpApiV3(process.env.NEXT_PUBLIC_AUTHORING_API_BASE ?? '/authoring')
    : mockApiV3;
