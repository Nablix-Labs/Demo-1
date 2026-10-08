'use client';

import PhaseGate from '@/components/PhaseGate';
import TopicParamRoute from '@/components/TopicParamRoute';
import TeachBackClient from './TeachBackClient';
import ConnectedTeachBackClient from './ConnectedTeachBackClient';

// `?topic=` rather than a path segment — see components/TopicParamRoute.
export default function Page() {
  return (
    <PhaseGate phase="teach">
      <TopicParamRoute render={(topicId) => process.env.NEXT_PUBLIC_API_BASE_URL
        ? <ConnectedTeachBackClient />
        : <TeachBackClient topicId={topicId} />} />
    </PhaseGate>
  );
}
