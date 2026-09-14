'use client';

/**
 * Resolving the topic for a topic-scoped screen, from the query string.
 *
 * These three screens used to be `/orientation/[topic]`, `/diagnostic/[topic]`
 * and `/teach/[topic]`. A dynamic segment cannot work here, because this app is
 * a STATIC EXPORT and every real topic id is a backend curriculum code
 * (`ALG-ORI-02`) from an open-ended set. `generateStaticParams` could only ever
 * enumerate the four mock ids, so no HTML and — the part that actually bit — no
 * RSC flight payload existed on disk for any real topic.
 *
 * That is not merely a deep-link problem. The App Router fetches a per-route
 * flight payload (`…/index.txt?_rsc=`) on a CLIENT-side push too, and nginx's
 * `try_files … /app/index.html` answers the miss with the app shell under a
 * 200. The router cannot tell that apart from a real payload, so
 * `router.push('/orientation/ALG-ORI-02')` navigated and then rendered the ROOT
 * GUIDED LESSON under the orientation URL — verified against the deployed build
 * on 13 Sep 2026, and the same failure shape as 28 July.
 *
 * A query param has one route, one HTML file and one flight payload, whatever
 * the topic is called, so it cannot go stale as the curriculum grows.
 *
 * The store is the fallback rather than an error: the id is already there for
 * a student who is mid-topic, so a link that loses the param resumes instead of
 * dead-ending.
 */

import { Suspense, type ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { useNumeraStore } from '@/store/useNumeraStore';

function Resolved({ render }: { render: (topicId: string) => ReactNode }) {
  const fromUrl = useSearchParams().get('topic')?.trim();
  const fromStore = useNumeraStore((s) => s.currentTopicId);
  const topicId = fromUrl || fromStore;
  if (!topicId) return <NoTopic />;
  return <>{render(topicId)}</>;
}

/**
 * No topic in the URL and none in progress. Deliberately not `notFound()`:
 * there is nothing missing, the link was simply incomplete, and a student who
 * lands here needs the way back rather than an error.
 */
function NoTopic() {
  return (
    <main
      className="flex-1 min-w-0 flex items-center justify-center bg-white p-8"
      aria-label="No topic selected"
    >
      <div className="max-w-[420px] text-center">
        <h1 className="text-[19px] font-semibold text-ink">No topic selected</h1>
        <p className="text-[13.5px] text-slate-blue leading-relaxed mt-2">
          This link doesn&apos;t say which topic to open. Pick one from your lessons and
          you&apos;ll carry on from where you left off.
        </p>
        <Link
          href="/"
          className="inline-flex items-center rounded-md bg-focus-navy px-5 py-2.5 text-[13px] font-semibold text-white hover:opacity-80 transition-opacity mt-5"
        >
          Back to my lessons
        </Link>
      </div>
    </main>
  );
}

/**
 * `useSearchParams` suspends during prerender, and an un-suspended call fails
 * the static export build outright — so the boundary lives here, once, rather
 * than being a thing each route has to remember.
 */
export default function TopicParamRoute({
  render,
}: {
  render: (topicId: string) => ReactNode;
}) {
  return (
    <Suspense fallback={null}>
      <Resolved render={render} />
    </Suspense>
  );
}
