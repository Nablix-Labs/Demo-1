import { redirect } from 'next/navigation';

export default async function TopicIndex({
  params,
}: {
  params: Promise<{ topicId: string }>;
}) {
  const { topicId } = await params;
  redirect(`/topics/${topicId}/details`);
}
