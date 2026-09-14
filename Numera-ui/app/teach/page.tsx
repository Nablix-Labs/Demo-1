'use client';

import PhaseGate from '@/components/PhaseGate';
import TopicParamRoute from '@/components/TopicParamRoute';
import TeachBackClient from './TeachBackClient';

// `?topic=` rather than a path segment — see components/TopicParamRoute.
export default function Page() {
  return (
    <PhaseGate phase="teach">
      <TopicParamRoute render={(topicId) => <TeachBackClient topicId={topicId} />} />
    </PhaseGate>
  );
}
