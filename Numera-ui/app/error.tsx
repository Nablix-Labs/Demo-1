'use client';

/**
 * The screen that used to be black.
 *
 * There was no error boundary anywhere in the app. In the App Router that is
 * not a missing nicety — an uncaught render throw unmounts the entire tree, and
 * what is left behind is the ambient backdrop in layout.tsx, which is dark. So
 * every render-time bug reached testing as "sometimes it goes mid black, no
 * response" (Manav, 21 Aug), with nothing on screen to say what happened and no
 * way forward but a manual reload.
 *
 * Two things matter here and they pull in opposite directions. The student
 * needs a way back into the lesson without being told anything alarming. We
 * need the stack, because a render throw leaves no network trace and the only
 * report we ever get is a photograph of a phone screen (see lib/failureReport).
 *
 * So the copy stays calm and the diagnostics go to the console, where the
 * digest — the id Next.js gives the error in a production build, and the only
 * handle on a minified stack — is printed alongside it.
 *
 * `reset()` re-renders the segment. That is genuinely enough for a throw caused
 * by one bad payload, because the store keeps the session and the next render
 * reads whatever arrived since. It is not enough for a throw that will simply
 * happen again, which is why "Back to the lesson" is offered next to it.
 */

import { useEffect } from 'react';
import Link from 'next/link';

export default function ErrorScreen({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[numera] render failed', {
      message: error.message,
      digest: error.digest,
      stack: error.stack,
      at: window.location.pathname,
      when: new Date().toISOString(),
    });
  }, [error]);

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="rounded-lg border border-muted-gray bg-white px-6 py-8 flex flex-col items-start gap-3 max-w-prose">
        <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">
          Something went wrong
        </div>
        <p className="text-[14px] text-ink leading-relaxed">
          This screen stopped responding. Nothing you have done has been lost —
          your session is still open. Try it again, and if it happens twice head
          back to the lesson.
        </p>
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={reset}
            className="inline-flex items-center rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity"
          >
            Try again
          </button>
          <Link
            href="/"
            className="inline-flex items-center rounded-md border border-muted-gray px-5 py-2.5 text-[13px] font-semibold text-ink hover:bg-slate-50 transition-colors"
          >
            Back to the lesson
          </Link>
        </div>
        {error.digest ? (
          <p className="text-[11px] text-slate-blue/70 font-mono">ref {error.digest}</p>
        ) : null}
      </div>
    </div>
  );
}
