import { CURRICULUM } from '@/lib/curriculum';
import DiagnosticClient from './DiagnosticClient';

// Static export — pre-render the per-topic diagnostic for every topic.
export function generateStaticParams() {
  return CURRICULUM.map((t) => ({ topic: t.id }));
}

export default function Page({ params }: { params: { topic: string } }) {
  return <DiagnosticClient topicId={params.topic} />;
}
