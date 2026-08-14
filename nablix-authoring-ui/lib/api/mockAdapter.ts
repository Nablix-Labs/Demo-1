import type { AuthoringApi } from './contracts';
import {
  COVERAGE_GRID_T02,
  STATS,
  TOPICS,
  WORKSPACE_T02,
} from './fixtures';
import { CONTENT_T02 } from './content-fixtures';
import { CURRICULUM, LIBRARY, REVIEW_QUEUE, SETTINGS } from './global-fixtures';

/** Simulate network latency so loading states are exercised in the demo. */
const delay = <T>(value: T, ms = 260): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), ms));

export const mockApi: AuthoringApi = {
  listTopics: () => delay(TOPICS),
  dashboardStats: () => delay(STATS),
  getWorkspace: (topicId) => {
    // Only T02 is fully authored in fixtures; other topics reuse its shape with
    // their own id so the workspace shell always renders.
    if (topicId === WORKSPACE_T02.details.topic_id) return delay(WORKSPACE_T02);
    const summary = TOPICS.find((t) => t.topic_id === topicId);
    return delay({
      ...WORKSPACE_T02,
      details: {
        ...WORKSPACE_T02.details,
        topic_id: topicId,
        topic_code: summary?.topic_code ?? topicId,
        topic_title: summary?.topic_title ?? WORKSPACE_T02.details.topic_title,
        ks_stage: summary?.ks_stage ?? WORKSPACE_T02.details.ks_stage,
        lifecycle: summary?.status ?? WORKSPACE_T02.details.lifecycle,
      },
      tree: { ...WORKSPACE_T02.tree, id: topicId },
    });
  },
  getContent: () => delay(CONTENT_T02),
  getLibrary: () => delay(LIBRARY),
  getCurriculum: () => delay(CURRICULUM),
  getReviewQueue: () => delay(REVIEW_QUEUE),
  getSettings: () => delay(SETTINGS),
  getCoverageGrid: () => delay(COVERAGE_GRID_T02),
  validateTopic: () => delay(WORKSPACE_T02.validation),
};
