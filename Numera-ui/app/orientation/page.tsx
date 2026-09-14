'use client';

import PhaseGate from '@/components/PhaseGate';
import TopicParamRoute from '@/components/TopicParamRoute';
import OrientationClient from './OrientationClient';

// `?topic=` rather than a path segment — see components/TopicParamRoute.
export default function Page() {
  return (
    <PhaseGate phase="orientation">
      <TopicParamRoute render={(topicId) => <OrientationClient topicId={topicId} />} />
    </PhaseGate>
  );
}
