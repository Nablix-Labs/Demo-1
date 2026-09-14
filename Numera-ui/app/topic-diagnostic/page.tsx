'use client';

/**
 * The per-topic readiness check that runs before each new topic.
 *
 * It lives here rather than under /diagnostic because /diagnostic is already
 * the one-time placement assessment — a different screen — so the query-param
 * move had nowhere to put this one. The path matches the FlowStage that has
 * always been called `topic-diagnostic`.
 */

import TopicParamRoute from '@/components/TopicParamRoute';
import DiagnosticClient from './DiagnosticClient';

export default function Page() {
  return <TopicParamRoute render={(topicId) => <DiagnosticClient topicId={topicId} />} />;
}
