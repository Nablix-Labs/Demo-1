/**
 * The page Next renders for any `notFound()` that is still reachable.
 *
 * Without a `not-found.tsx` anywhere in the tree, `notFound()` in a client
 * component unmounts the children inside AppFrame and leaves an empty div —
 * a blank white page with nothing on it and no way out. That is what a student
 * finishing a topic saw when `next_topic_handoff` sent them to a backend topic
 * code the mock curriculum does not list (11 Sep 2026).
 *
 * The codes themselves are handled properly now — see `lib/topicDisplay` — so
 * this is the floor under the remaining mock-mode cases rather than the fix.
 * It exists so the next unhandled id is a readable screen instead of a blank
 * one.
 */

import Link from 'next/link';

export default function NotFound() {
  return (
    <main
      className="flex-1 min-w-0 flex items-center justify-center bg-white p-8"
      aria-label="Page not found"
    >
      <div className="max-w-[420px] text-center">
        <h1 className="text-[19px] font-semibold text-ink">We couldn&apos;t find that page</h1>
        <p className="text-[13.5px] text-slate-blue leading-relaxed mt-2">
          The link may be out of date. Your work is saved — head back to your lessons and
          pick up where you left off.
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
