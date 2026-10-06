'use client';

import { useEffect, useState } from 'react';

/**
 * Runs a library loader once on mount. `data` stays null while loading and on
 * failure; `error` carries the failure message so the page can say so instead
 * of sitting on a skeleton forever.
 */
export function useLibrary<T>(load: () => Promise<T>): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    load()
      .then((d) => live && setData(d))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
    // The loaders are module-level functions; run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { data, error };
}
