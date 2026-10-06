'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, ChevronDown, LogOut } from 'lucide-react';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { DashboardTopicRow } from '@/lib/api/v3-contracts';
import { BASE_PATH, signedInEmail, signOut } from '@/lib/auth';

/** Two letters from the local part of the email ("jane.doe@…" → "JD"). */
function initials(email: string | null): string {
  if (!email) return '?';
  const parts = email.split('@')[0].split(/[._\-+]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : (parts[0] ?? '').slice(0, 2);
  return letters.toUpperCase() || '?';
}

/**
 * Jump to a topic by code, title or id. The topic list is the dashboard's, loaded
 * once on first focus; Enter opens the first match's details page.
 */
function TopicSearch() {
  const router = useRouter();
  const [topics, setTopics] = useState<DashboardTopicRow[] | null>(null);
  const [query, setQuery] = useState('');
  const [miss, setMiss] = useState(false);
  const loading = useRef<Promise<DashboardTopicRow[]> | null>(null);

  function load(): Promise<DashboardTopicRow[]> {
    if (topics) return Promise.resolve(topics);
    loading.current ??= apiV3.getDashboard().then((d) => {
      setTopics(d.topics);
      return d.topics;
    });
    return loading.current;
  }

  async function go() {
    const q = query.trim().toLowerCase();
    if (!q) return;
    let list: DashboardTopicRow[];
    try {
      list = await load();
    } catch {
      loading.current = null;
      setMiss(true);
      return;
    }
    const hit =
      list.find((t) => t.topic_code.toLowerCase() === q || t.topic_id.toLowerCase() === q) ??
      list.find((t) => t.topic_code.toLowerCase().includes(q) || t.title.toLowerCase().includes(q));
    if (!hit) {
      setMiss(true);
      return;
    }
    setQuery('');
    router.push(`/topics/${hit.topic_id}/details`);
  }

  return (
    <div className="lg-glass hidden items-center gap-2 rounded-pill px-3.5 py-2 md:flex">
      <Search className="h-4 w-4 text-slate-blue" />
      <input
        className="w-52 bg-transparent text-sm text-ink placeholder:text-slate-blue/60 focus:outline-none"
        placeholder="Go to topic by code or title…"
        list="topbar-topics"
        value={query}
        onFocus={() => void load().catch(() => (loading.current = null))}
        onChange={(e) => {
          setQuery(e.target.value);
          setMiss(false);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void go();
        }}
      />
      {miss && <span className="text-2xs font-semibold text-danger">No match</span>}
      <datalist id="topbar-topics">
        {topics?.map((t) => <option key={t.topic_id} value={t.topic_code}>{t.title}</option>)}
      </datalist>
    </div>
  );
}

function Account() {
  // sessionStorage is read after mount so the server render and first client
  // render agree.
  const [email, setEmail] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => setEmail(signedInEmail()), []);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const badge = (
    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-focus-navy text-2xs font-bold text-white">
      {initials(email)}
    </span>
  );

  // No signed-in approver (mock mode): nothing to sign out of.
  if (!email) {
    return (
      <span className="rounded-pill border border-muted-gray bg-white p-1" title="Not signed in">
        {badge}
      </span>
    );
  }

  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={email}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-pill border border-muted-gray bg-white py-1 pl-1 pr-2.5 transition-colors hover:bg-reading-surface"
      >
        {badge}
        <ChevronDown className="h-3.5 w-3.5 text-slate-blue" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-20 mt-2 min-w-[220px] border border-muted-gray bg-white py-1 shadow-card">
          <div className="truncate px-3.5 py-2 text-2xs text-slate-blue">{email}</div>
          <button
            role="menuitem"
            onClick={() => {
              signOut();
              window.location.assign(`${BASE_PATH}/login`);
            }}
            className="flex w-full items-center gap-2 px-3.5 py-2 text-left text-sm font-semibold text-focus-navy hover:bg-reading-surface"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Topbar({
  title,
  crumb,
}: {
  title: string;
  crumb?: string;
}) {
  return (
    <header className="relative z-10 flex h-16 shrink-0 items-center gap-4 px-6">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <h1 className="truncate font-display text-lg font-bold tracking-tight text-focus-navy">{title}</h1>
          {crumb && (
            <>
              <span className="text-slate-blue/40">/</span>
              <span className="truncate text-sm font-medium text-slate-blue">{crumb}</span>
            </>
          )}
        </div>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <TopicSearch />
        <Account />
      </div>
    </header>
  );
}
