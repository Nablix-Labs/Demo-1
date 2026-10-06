'use client';

/**
 * Keeps the portal behind the approver login in `http` mode.
 *
 * /login renders full-screen, without the sidebar. Every other route needs a
 * token; without one the approver is sent to /login and brought back after.
 * The mock (no NEXT_PUBLIC_API_MODE) needs no login and renders straight away.
 */

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Sidebar } from '@/components/nablix/Sidebar';
import { API_ERROR_EVENT, authRequired, getToken, redirectToLogin } from '@/lib/auth';

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const onLogin = pathname.startsWith('/login');
  // Decided after mount: the token lives in sessionStorage, which the server
  // render cannot see.
  const [allowed, setAllowed] = useState(!authRequired);

  useEffect(() => {
    if (!authRequired || onLogin) return;
    if (getToken()) setAllowed(true);
    else redirectToLogin();
  }, [onLogin, pathname]);

  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => {
    const show = (e: Event) => setLoadError((e as CustomEvent<string>).detail);
    window.addEventListener(API_ERROR_EVENT, show);
    return () => window.removeEventListener(API_ERROR_EVENT, show);
  }, []);
  // A new page is a new load; the last page's failure no longer applies.
  useEffect(() => setLoadError(null), [pathname]);

  if (onLogin) return <>{children}</>;
  if (!allowed) return null;

  return (
    <div className="relative z-10 flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {loadError && (
          <div role="alert" className="mx-6 mt-4 flex items-center justify-between gap-3 rounded-btn border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
            <span>{loadError}</span>
            <button className="font-semibold underline" onClick={() => window.location.reload()}>Retry</button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
