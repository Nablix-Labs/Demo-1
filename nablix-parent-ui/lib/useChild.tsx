'use client';

/**
 * The selected child's data and the date range, shared by every page.
 *
 * Loaded once per child; switching pages reuses it. The range (7 / 30 / 90
 * days) is remembered in the browser as a convenience.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Child, ChildData } from './types';
import { listChildren, loadChild, ApiError } from './api';
import { rangeEndingToday, type Range } from './derive';

const RANGE_KEY = 'nablix.parent.range';
const CHILD_KEY = 'nablix.parent.child';
export const RANGES = [7, 30, 90] as const;

interface Ctx {
  children: Child[];
  data: ChildData | null;
  error: string | null;
  needsLogin: boolean;
  range: Range;
  setDays: (d: number) => void;
  selectChild: (code: string) => void;
  reload: () => void;
  /** Re-render after an in-place change (e.g. a consent toggle). */
  touch: () => void;
}

const ChildContext = createContext<Ctx | null>(null);

export function ChildProvider({ children: ui }: { children: ReactNode }) {
  const [kids, setKids] = useState<Child[]>([]);
  const [code, setCode] = useState<string | null>(null);
  const [data, setData] = useState<ChildData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [days, setDaysState] = useState(7);
  const [nonce, setNonce] = useState(0);
  // Bumped after data is changed in place (a consent toggle) to re-render readers.
  const [tick, setTick] = useState(0);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(RANGE_KEY));
      if ((RANGES as readonly number[]).includes(saved)) setDaysState(saved);
    } catch { /* storage blocked: keep the default */ }
  }, []);

  const fail = (e: unknown) => {
    if (e instanceof ApiError && e.status === 401) setNeedsLogin(true);
    setError(e instanceof Error ? e.message : 'Something went wrong.');
  };

  useEffect(() => {
    setError(null);
    listChildren()
      .then((list) => {
        setKids(list);
        let saved: string | null = null;
        try { saved = localStorage.getItem(CHILD_KEY); } catch { /* storage blocked */ }
        setCode((c) => c ?? list.find((k) => k.student_code === saved)?.student_code ?? list[0]?.student_code ?? null);
        if (!list.length) setError('No child is linked to this account yet.');
      })
      .catch(fail);
  }, [nonce]);

  useEffect(() => {
    if (!code) return;
    setData(null);
    loadChild(code).then(setData).catch(fail);
  }, [code, nonce]);

  const setDays = useCallback((d: number) => {
    setDaysState(d);
    try { localStorage.setItem(RANGE_KEY, String(d)); } catch { /* ignore */ }
  }, []);

  const value = useMemo<Ctx>(() => ({
    children: kids,
    data,
    error,
    needsLogin,
    range: rangeEndingToday(days),
    setDays,
    selectChild: (next: string) => {
      setCode(next);
      try { localStorage.setItem(CHILD_KEY, next); } catch { /* not remembered */ }
    },
    reload: () => setNonce((n) => n + 1),
    touch: () => setTick((t) => t + 1),
  }), [kids, data, error, needsLogin, days, setDays, tick]);

  return <ChildContext.Provider value={value}>{ui}</ChildContext.Provider>;
}

export function useChild(): Ctx {
  const ctx = useContext(ChildContext);
  if (!ctx) throw new Error('useChild outside ChildProvider');
  return ctx;
}
