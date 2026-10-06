'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

// The Dashboard is the topic list; the Topics nav item routes there.
export default function TopicsPage() {
  const router = useRouter();
  useEffect(() => router.replace('/'), [router]);
  return null;
}
