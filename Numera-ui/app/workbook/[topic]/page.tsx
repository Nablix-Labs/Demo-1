import { CURRICULUM } from '@/lib/curriculum';
import PhaseGate from '@/components/PhaseGate';
import TopicClient from './TopicClient';

// Static export — pre-render a page for every topic in the curriculum.
export function generateStaticParams() {
  return CURRICULUM.map((t) => ({ topic: t.id }));
}

export default function Page({ params }: { params: { topic: string } }) {
  return (
    <PhaseGate phase="workbook">
      <TopicClient topicId={params.topic} />
    </PhaseGate>
  );
}
