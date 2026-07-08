import { CURRICULUM } from '@/lib/curriculum';
import PhaseGate from '@/components/PhaseGate';
import TopicClient from './TopicClient';

// Static export — pre-render a page for every topic in the curriculum.
export function generateStaticParams() {
  return CURRICULUM.map((t) => ({ topic: t.id }));
}

export default async function Page({ params }: { params: Promise<{ topic: string }> }) {
  const { topic } = await params;
  return (
    <PhaseGate phase="workbook">
      <TopicClient topicId={topic} />
    </PhaseGate>
  );
}
