'use client';

import { usePathname } from 'next/navigation';

/**
 * The topic in the URL: `/topics/<id>/...`.
 *
 * Read from the path, not `useParams`. On the VM the portal is a static export
 * with a page built for one placeholder topic (`_`), and nginx serves that page
 * for any topic id — so the params baked into the page say `_` while the URL
 * says the real topic. The URL is the truth.
 */
export function useTopicId(): string {
  const pathname = usePathname();
  const match = pathname.match(/\/topics\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}
