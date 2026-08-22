'use client';

/**
 * The boundary of last resort.
 *
 * app/error.tsx catches throws inside a page, but not throws inside the root
 * layout itself — and the root layout is where AppFrame does store hydration
 * and the auth gate, which is exactly the code that runs before anything is on
 * screen. A throw there produced the same black screen with no boundary above
 * it to say so.
 *
 * This replaces the root layout when it renders, so it owns its own <html> and
 * <body> and cannot rely on globals.css having been loaded. Hence inline
 * styles: a fallback that depends on the stylesheet the failure may have
 * prevented is not a fallback.
 *
 * Deliberately plainer than app/error.tsx. If this one is showing, the shell
 * did not come up, and the honest offer is a reload rather than a link into an
 * app that just failed to start.
 */

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[numera] app shell failed', {
      message: error.message,
      digest: error.digest,
      stack: error.stack,
      when: new Date().toISOString(),
    });
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, background: '#ffffff', color: '#1a1f2b',
        font: '15px/1.6 system-ui, -apple-system, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center',
          justifyContent: 'center', padding: 32 }}>
          <div style={{ maxWidth: 480 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.12em',
              textTransform: 'uppercase', color: '#5b6b8c' }}>
              Numera could not start
            </div>
            <p style={{ marginTop: 12 }}>
              Something went wrong loading the app. Reloading usually fixes it —
              your work is saved on our side, not in this page.
            </p>
            <button
              onClick={reset}
              style={{ marginTop: 16, padding: '10px 20px', fontSize: 13,
                fontWeight: 600, color: '#fff', background: '#1e3a5f',
                border: 0, borderRadius: 6, cursor: 'pointer' }}
            >
              Reload
            </button>
            {error.digest ? (
              <p style={{ marginTop: 16, fontSize: 11, color: '#8a94a6',
                fontFamily: 'ui-monospace, monospace' }}>ref {error.digest}</p>
            ) : null}
          </div>
        </div>
      </body>
    </html>
  );
}
