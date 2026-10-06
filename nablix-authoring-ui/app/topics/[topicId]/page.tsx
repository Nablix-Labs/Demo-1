'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTopicId } from '@/lib/useTopicId';

/** A topic opens on its details tab. Client-side, so it works in the static export. */
export default function TopicIndex() {
  const router = useRouter();
  const topicId = useTopicId();
  useEffect(() => {
    if (topicId) router.replace(`/topics/${encodeURIComponent(topicId)}/details`);
  }, [router, topicId]);
  return null;
}
