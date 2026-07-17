import { CURRICULUM } from '@/lib/curriculum';
import PhaseGate from '@/components/PhaseGate';
import TeachBackClient from './TeachBackClient';

// Static export — pre-render Teacher Mode for every topic.
export function generateStaticParams() {
  return CURRICULUM.map((t) => ({ topic: t.id }));
}

export default async function Page({ params }: { params: Promise<{ topic: string }> }) {
  const { topic } = await params;
  return (
    <PhaseGate phase="teach">
      <TeachBackClient topicId={topic} />
    </PhaseGate>
  );
}
