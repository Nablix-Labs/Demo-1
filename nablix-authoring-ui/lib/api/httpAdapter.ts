import type {
  AuthoringApi,
  CoverageGrid,
  CurriculumNode,
  DashboardStats,
  GlobalLibrary,
  ReviewItem,
  SettingsData,
  TopicContent,
  TopicSummary,
  TopicWorkspace,
  ValidationIssue,
} from './contracts';

/**
 * Real backend adapter (spec §16). Inactive until the authoring endpoints ship;
 * selected via NEXT_PUBLIC_API_MODE=http. Endpoint paths follow the spec exactly.
 */
export function createHttpApi(base: string): AuthoringApi {
  const get = async <T>(path: string): Promise<T> => {
    const res = await fetch(`${base}${path}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`Authoring API ${path} failed: ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as T;
  };
  const post = async <T>(path: string): Promise<T> => {
    const res = await fetch(`${base}${path}`, { method: 'POST' });
    if (!res.ok) {
      throw new Error(`Authoring API ${path} failed: ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as T;
  };

  return {
    listTopics: () => get<TopicSummary[]>('/topics'),
    dashboardStats: () => get<DashboardStats>('/stats'),
    getWorkspace: (topicId) => get<TopicWorkspace>(`/topics/${topicId}/workspace`),
    getContent: (topicId) => get<TopicContent>(`/topics/${topicId}/content`),
    getLibrary: () => get<GlobalLibrary>('/library'),
    getCurriculum: () => get<CurriculumNode[]>('/curriculum'),
    getReviewQueue: () => get<ReviewItem[]>('/review-queue'),
    getSettings: () => get<SettingsData>('/settings'),
    getCoverageGrid: (topicId) => get<CoverageGrid>(`/topics/${topicId}/coverage`),
    validateTopic: (topicId) => post<ValidationIssue[]>(`/topics/${topicId}/validate`),
  };
}
