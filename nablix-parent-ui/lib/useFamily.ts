'use client';

/**
 * Every linked child's data at once, for the family screens.
 *
 * The rest of the portal shows one child (useChild); comparing siblings needs
 * them all. Loaded on demand and in parallel, so one child's failure is shown
 * on that child's card rather than blanking the page.
 */
import { useEffect, useState } from 'react';
import { loadChild } from './api';
import { useChild } from './useChild';
import type { ChildData } from './types';

export type FamilyEntry =
  | { code: string; status: 'loading' }
  | { code: string; status: 'ready'; data: ChildData }
  | { code: string; status: 'error'; message: string };

export function useFamily(): FamilyEntry[] {
  const { children } = useChild();
  const [entries, setEntries] = useState<FamilyEntry[]>([]);
  const codes = children.map((c) => c.student_code).join('|');

  useEffect(() => {
    let cancelled = false;
    const list = codes ? codes.split('|') : [];
    setEntries(list.map((code) => ({ code, status: 'loading' })));
    list.forEach((code, i) => {
      loadChild(code)
        .then((data) => !cancelled && setEntries((prev) => prev.map((e, j) => (j === i ? { code, status: 'ready', data } : e))))
        .catch((e: unknown) => !cancelled && setEntries((prev) => prev.map((x, j) => (j === i
          ? { code, status: 'error', message: e instanceof Error ? e.message : 'Could not load.' }
          : x))));
    });
    return () => { cancelled = true; };
  }, [codes]);

  return entries;
}
