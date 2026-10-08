'use client';

/**
 * App frame: sidebar, top bar, the sample-data notice, and the loading,
 * error and signed-out states every page would otherwise repeat.
 */
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';
import clsx from 'clsx';
import {
  LayoutGrid, BookOpen, Route, Sparkles, ListChecks, CalendarClock, FileText, ShieldCheck, Settings,
  LogOut, Info, RotateCw, Download, Menu, X,
} from 'lucide-react';
import { ChildProvider, useChild, RANGES } from '@/lib/useChild';
import { getToken, isSample, signOut, BASE_PATH } from '@/lib/api';
import { Segments, PillButton } from './ui';
import type { ChildData } from '@/lib/types';

const NAV = [
  { href: '/', label: 'Overview', icon: LayoutGrid },
  { href: '/topics', label: 'Topics', icon: BookOpen },
  { href: '/journey', label: 'Learning journey', icon: Route },
  { href: '/skills', label: 'Strengths & weaknesses', icon: Sparkles },
  { href: '/next-steps', label: 'Next steps', icon: ListChecks },
  { href: '/activity', label: 'Activity', icon: CalendarClock },
  { href: '/reports', label: 'Reports', icon: FileText },
  { href: '/consent', label: 'Consent & privacy', icon: ShieldCheck },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Logo({ onDark }: { onDark?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 40 40" className="h-10 w-10" aria-hidden>
        <rect width="40" height="40" rx="13" fill="#1F1D1A" />
        <path d="M12 28V12l16 16V12" fill="none" stroke="#F8F5E4" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="30" cy="10" r="4" fill="#F4B63F" />
      </svg>
      <span className="leading-none">
        <span className={clsx('block text-[19px] font-black tracking-[-0.02em]', onDark ? 'text-white' : 'text-ink')}>Numera</span>
        <span className={clsx('mt-0.5 block text-[11px] font-extrabold', onDark ? 'text-white/70' : 'text-ink-soft')}>for parents</span>
      </span>
    </span>
  );
}

export const initials = (name: string) => name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const path = usePathname();
  const { data } = useChild();
  const active = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
  return (
    <aside
      className={clsx(
        'no-print fixed inset-y-0 left-0 z-30 flex w-[264px] flex-col overflow-y-auto bg-cream px-4 py-6 transition-transform lg:translate-x-0',
        open ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
      )}
    >
      <div className="flex items-center justify-between px-2">
        <Link href="/" onClick={onClose}><Logo /></Link>
        <button className="rounded-full bg-cream-deep p-2 text-ink lg:hidden" onClick={onClose} aria-label="Close menu">
          <X size={18} />
        </button>
      </div>

      {data && (
        <div className="mt-6 flex items-center gap-3 rounded-[22px] bg-card px-3 py-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-full border-[3px] border-white bg-mustard text-[15px] font-black text-ink">
            {initials(data.child.name)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-extrabold text-ink">{data.child.name}</span>
            <span className="block text-[12.5px] font-bold text-ink-soft">{data.child.year_group}</span>
          </span>
        </div>
      )}

      <nav className="mt-5 flex flex-col gap-1" aria-label="Main">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            onClick={onClose}
            aria-current={active(href) ? 'page' : undefined}
            className={clsx(
              'flex items-center gap-3 rounded-full px-3 py-2 text-[14px] font-extrabold transition-colors',
              active(href) ? 'bg-ink text-white' : 'text-ink-soft hover:bg-cream-deep hover:text-ink',
            )}
          >
            <span className={clsx('flex h-8 w-8 items-center justify-center rounded-full', active(href) ? 'bg-white/15' : 'bg-cream-deep')}>
              <Icon size={16} strokeWidth={2.4} aria-hidden />
            </span>
            {label}
          </Link>
        ))}
      </nav>

      <div className="mt-auto pt-6">
        {!isSample && (
          <button
            onClick={() => { signOut(); window.location.assign(`${BASE_PATH}/login/`); }}
            className="flex w-full items-center gap-3 rounded-full px-3 py-2 text-[14px] font-extrabold text-ink-soft hover:bg-cream-deep"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-cream-deep"><LogOut size={16} strokeWidth={2.4} aria-hidden /></span>
            Sign out
          </button>
        )}
      </div>
    </aside>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const { children: kids, data, range, setDays, selectChild } = useChild();
  return (
    <div className="no-print mb-6 flex flex-wrap items-center gap-3">
      <button className="rounded-full bg-card p-2.5 text-ink lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu size={18} />
      </button>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {kids.length > 1 && (
          <select
            aria-label="Child"
            value={data?.child.student_code}
            onChange={(e) => selectChild(e.target.value)}
            className="rounded-full bg-card px-4 py-2.5 text-[13.5px] font-extrabold text-ink"
          >
            {kids.map((k) => <option key={k.student_code} value={k.student_code}>{k.name}</option>)}
          </select>
        )}
        <div className="w-[300px] rounded-full bg-card p-1">
          <Segments label="Date range" options={RANGES.map((d) => ({ value: d, label: `${d} days` }))} value={range.days as 7 | 30 | 90} onChange={setDays} />
        </div>
        <PillButton href="/reports" icon={<Download size={14} strokeWidth={2.6} />}>Report</PillButton>
      </div>
    </div>
  );
}

function Frame({ children }: { children: (d: ChildData) => ReactNode }) {
  const { data, error, needsLogin, reload } = useChild();
  const [menu, setMenu] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (needsLogin) router.replace('/login');
  }, [needsLogin, router]);

  return (
    <div className="min-h-screen overflow-x-hidden">
      <Sidebar open={menu} onClose={() => setMenu(false)} />
      {menu && <div className="fixed inset-0 z-20 bg-ink/30 lg:hidden" onClick={() => setMenu(false)} />}
      <main className="print-full px-4 py-6 sm:px-8 lg:ml-[264px]">
        <div className="print-full mx-auto max-w-[1240px]">
          <Topbar onMenu={() => setMenu(true)} />
          {isSample && (
            <div className="no-print mb-6 flex items-start gap-3 rounded-[22px] bg-mustard-soft px-4 py-3 text-[13px] font-semibold text-ink">
              <Info size={17} className="mt-0.5 flex-shrink-0" aria-hidden />
              <span>
                <b className="font-extrabold">Sample data.</b> This preview shows a made-up student. Real progress appears here once parent
                accounts are connected to Numera.
              </span>
            </div>
          )}
          {error ? (
            <div className="rounded-card bg-coral-soft p-8 text-center">
              <p className="text-[17px] font-extrabold text-ink">{error}</p>
              <PillButton onClick={reload} icon={<RotateCw size={14} strokeWidth={2.6} />} className="mt-4">Try again</PillButton>
            </div>
          ) : data ? (
            children(data)
          ) : (
            <div className="grid gap-4 md:grid-cols-3" aria-busy="true" aria-label="Loading">
              {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="h-44 animate-pulse rounded-card bg-card" />)}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

/** Wrap a page: `<Shell>{(data) => …}</Shell>`. */
export default function Shell({ children }: { children: (d: ChildData) => ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(isSample);
  useEffect(() => {
    if (isSample) return;
    if (!getToken()) router.replace('/login');
    else setReady(true);
  }, [router]);
  if (!ready) return null;
  return (
    <ChildProvider>
      <Frame>{children}</Frame>
    </ChildProvider>
  );
}
