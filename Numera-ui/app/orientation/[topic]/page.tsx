import { CURRICULUM } from '@/lib/curriculum';
import PhaseGate from '@/components/PhaseGate';
import OrientationClient from './OrientationClient';

// Static export — pre-render orientation for every topic.
export function generateStaticParams() {
  return CURRICULUM.map((t) => ({ topic: t.id }));
}

export default function Page({ params }: { params: { topic: string } }) {
  return (
    <PhaseGate phase="orientation">
      <OrientationClient topicId={params.topic} />
    </PhaseGate>
  );
}
