'use client';

/**
 * App frame: sidebar, top bar, the sample-data notice, and the loading,
 * error and signed-out states every page would otherwise repeat.
 */
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import clsx from 'clsx';
import {
  LayoutDashboard, BookOpen, Map, Target, ListChecks, CalendarDays, FileText, ShieldCheck, Settings,
  LogOut, Info, RotateCw, Download, Menu, X, PanelLeftClose, PanelLeftOpen, Users, ChevronsUpDown, Check,
} from 'lucide-react';
import { childLook } from '@/lib/childColor';
import { ChildProvider, useChild, RANGES } from '@/lib/useChild';
import { getToken, isSample, signOut, BASE_PATH } from '@/lib/api';
import { Segments, PillButton } from './ui';
import type { ChildData } from '@/lib/types';

const NAV = [
  {
    section: 'Progress',
    items: [
      { href: '/family', label: 'Family', icon: Users, family: true },
      { href: '/', label: 'Overview', icon: LayoutDashboard },
      { href: '/topics', label: 'Topics', icon: BookOpen },
      { href: '/journey', label: 'Learning journey', icon: Map },
      { href: '/skills', label: 'Strengths & weaknesses', icon: Target },
      { href: '/next-steps', label: 'Next steps', icon: ListChecks },
      { href: '/activity', label: 'Activity', icon: CalendarDays },
    ],
  },
  {
    section: 'Account',
    items: [
      { href: '/reports', label: 'Reports', icon: FileText },
      { href: '/consent', label: 'Consent & privacy', icon: ShieldCheck },
      { href: '/settings', label: 'Settings', icon: Settings },
    ],
  },
];

const COLLAPSE_KEY = 'nablix.parent.sidebar-collapsed';

export function Logo({ onDark, markOnly }: { onDark?: boolean; markOnly?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 40 40" className="h-9 w-9 flex-shrink-0" aria-hidden>
        <rect width="40" height="40" rx="13" fill="#1F1D1A" />
        <path d="M12 28V12l16 16V12" fill="none" stroke="#F8F5E4" strokeWidth="3.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="30" cy="10" r="4" fill="#F4B63F" />
      </svg>
      {!markOnly && <span className="leading-none">
        <span className={clsx('block text-[19px] font-black tracking-[-0.02em]', onDark ? 'text-white' : 'text-ink')}>Numera</span>
        <span className={clsx('mt-0.5 block text-[11px] font-extrabold', onDark ? 'text-white/70' : 'text-ink-soft')}>for parents</span>
      </span>}
    </span>
  );
}

const plainInitials = (name: string) => name.split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();

/**
 * Avatar letters. Siblings usually share a surname, so Arjun and Anaya Sharma
 * would both be "AS"; when initials clash within the family, use the first two
 * letters of the first name instead ("Ar", "An").
 */
export function initials(name: string, family: string[] = []): string {
  const mine = plainInitials(name);
  const clash = family.some((other) => other !== name && plainInitials(other) === mine);
  if (!clash) return mine;
  const first = name.trim().split(/\s+/)[0] ?? name;
  return first.slice(0, 1).toUpperCase() + first.slice(1, 2).toLowerCase();
}

/**
 * The child this portal is showing, and the way to switch to a sibling.
 *
 * One child: a plain card. Several: the card opens a list of every child, each
 * in their own colour, with a link to the family view. In the collapsed rail it
 * is the avatars, stacked.
 */
function ChildSwitcher({ rail, onPicked }: { rail: boolean; onPicked: () => void }) {
  const { data, children: kids, selectChild } = useChild();
  const [open, setOpen] = useState(false);
  // In the rail the list sits beside the sidebar, which clips overflow, so it
  // is positioned against the viewport instead.
  const [railPos, setRailPos] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [open]);
  if (!data) return null;
  const index = Math.max(0, kids.findIndex((k) => k.student_code === data.child.student_code));
  const many = kids.length > 1;
  const avatar = (name: string, i: number, size = 'h-10 w-10 text-[13px]') => (
    <span className={clsx('flex flex-shrink-0 items-center justify-center rounded-full font-black ring-2 ring-cream', size, childLook(i).avatar)}>
      {initials(name, kids.map((k) => k.name))}
    </span>
  );

  return (
    <div ref={ref} className="relative mt-5">
      <button
        type="button"
        disabled={!many}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setRailPos({ top: r.top, left: r.right + 12 });
          setOpen((o) => !o);
        }}
        aria-haspopup={many ? 'listbox' : undefined}
        aria-expanded={many ? open : undefined}
        aria-label={many ? `Showing ${data.child.name}. Switch child` : data.child.name}
        title={rail ? `${data.child.name}, ${data.child.year_group}` : undefined}
        className={clsx(
          'flex w-full items-center gap-3 rounded-[16px] text-left transition-colors',
          rail ? 'justify-center py-1' : 'bg-card px-2.5 py-2.5',
          many && !rail && 'hover:bg-white',
        )}
      >
        {rail && many ? (
          <span className="flex flex-col items-center -space-y-3">
            {avatar(data.child.name, index)}
            {kids.filter((k) => k.student_code !== data.child.student_code).slice(0, 2).map((k) => (
              <span key={k.student_code} className="scale-75 opacity-90">{avatar(k.name, kids.indexOf(k))}</span>
            ))}
          </span>
        ) : avatar(data.child.name, index)}
        {!rail && (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-extrabold text-ink">{data.child.name}</span>
            <span className="block text-[12px] font-bold text-ink-soft">
              {data.child.year_group}{many ? ` · ${kids.length} children` : ''}
            </span>
          </span>
        )}
        {!rail && many && <ChevronsUpDown size={16} className="flex-shrink-0 text-ink-soft" aria-hidden />}
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Your children"
          className={clsx(
            'z-50 rounded-[20px] bg-card p-2 shadow-[0_18px_50px_rgba(31,29,26,0.18)] ring-1 ring-line',
            // Expanded: the sidebar's own width (it clips anything wider).
            rail ? 'fixed w-[260px]' : 'absolute inset-x-0 top-full mt-2',
          )}
          style={rail && railPos ? { top: railPos.top, left: railPos.left } : undefined}
        >
          <p className="px-3 pb-1.5 pt-1 text-[11px] font-extrabold uppercase tracking-[0.08em] text-ink-soft/70">Your children</p>
          {kids.map((k, i) => {
            const on = k.student_code === data.child.student_code;
            return (
              <button
                key={k.student_code}
                role="option"
                aria-selected={on}
                onClick={() => { selectChild(k.student_code); setOpen(false); onPicked(); }}
                className={clsx('flex w-full items-center gap-3 rounded-[14px] px-2.5 py-2 text-left transition-colors', on ? 'bg-cream' : 'hover:bg-cream')}
              >
                {avatar(k.name, i, 'h-9 w-9 text-[12px]')}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-extrabold text-ink">{k.name}</span>
                  <span className="block text-[12px] font-bold text-ink-soft">{k.year_group}</span>
                </span>
                {on && <Check size={16} strokeWidth={2.6} className="text-teal" aria-hidden />}
              </button>
            );
          })}
          <Link
            href="/family"
            onClick={() => { setOpen(false); onPicked(); }}
            className="mt-1 flex items-center justify-center gap-2 rounded-[14px] bg-ink px-3 py-2.5 text-[13px] font-extrabold text-white"
          >
            <Users size={15} aria-hidden /> See the whole family
          </Link>
        </div>
      )}
    </div>
  );
}

/**
 * Collapsible on desktop (an icon rail, remembered per browser); a drawer on
 * phones. Plain icons and one quiet active state: the page title says where you
 * are, the sidebar only has to say where else you can go.
 */
function Sidebar({ open, onClose, collapsed, onToggle }: {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const path = usePathname();
  const { data, children: kids } = useChild();
  const active = (href: string) => (href === '/' ? path === '/' : path.startsWith(href));
  // The drawer on phones is always full width; only the desktop rail collapses.
  const rail = collapsed && !open;
  return (
    <aside
      aria-label="Sidebar"
      className={clsx(
        'no-print fixed inset-y-0 left-0 z-30 flex flex-col overflow-y-auto overflow-x-hidden border-r border-line bg-cream py-5 transition-[width,transform] duration-200 lg:translate-x-0',
        rail ? 'w-[76px] px-3' : 'w-[248px] px-4',
        open ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
      )}
    >
      <div className={clsx('flex items-center', rail ? 'flex-col gap-3' : 'justify-between px-1')}>
        <Link href="/" onClick={onClose} aria-label="Numera for parents, overview"><Logo markOnly={rail} /></Link>
        <button
          onClick={open ? onClose : onToggle}
          aria-label={open ? 'Close menu' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={open ? 'Close menu' : collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex h-8 w-8 items-center justify-center rounded-[10px] text-ink-soft transition-colors hover:bg-cream-deep hover:text-ink"
        >
          {open ? <X size={18} /> : collapsed ? <PanelLeftOpen size={18} strokeWidth={2} /> : <PanelLeftClose size={18} strokeWidth={2} />}
        </button>
      </div>

      {data && <ChildSwitcher rail={rail} onPicked={onClose} />}

      <nav className="mt-5 flex flex-col gap-5" aria-label="Main">
        {NAV.map(({ section, items }) => (
          <div key={section} className="flex flex-col gap-0.5">
            {rail
              ? <span aria-hidden className="mx-auto mb-1 h-px w-6 bg-line" />
              : <span className="mb-1 px-3 text-[11px] font-extrabold uppercase tracking-[0.08em] text-ink-soft/70">{section}</span>}
            {items.filter((item) => !('family' in item) || kids.length > 1).map(({ href, label, icon: Icon }) => {
              const on = active(href);
              return (
                <Link
                  key={href}
                  href={href}
                  onClick={onClose}
                  aria-current={on ? 'page' : undefined}
                  aria-label={rail ? label : undefined}
                  title={rail ? label : undefined}
                  className={clsx(
                    'group relative flex items-center rounded-[12px] text-[14px] font-bold transition-colors',
                    rail ? 'h-11 justify-center' : 'gap-3 px-3 py-2.5',
                    on ? 'bg-card text-ink' : 'text-ink-soft hover:bg-cream-deep/70 hover:text-ink',
                  )}
                >
                  {on && <span aria-hidden className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-teal" />}
                  <Icon size={18} strokeWidth={on ? 2.3 : 1.9} aria-hidden className="flex-shrink-0" />
                  {!rail && <span className="truncate">{label}</span>}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {!isSample && (
        <div className="mt-auto pt-6">
          <button
            onClick={() => { signOut(); window.location.assign(`${BASE_PATH}/login/`); }}
            aria-label={rail ? 'Sign out' : undefined}
            title={rail ? 'Sign out' : undefined}
            className={clsx(
              'flex w-full items-center rounded-[12px] text-[14px] font-bold text-ink-soft transition-colors hover:bg-cream-deep/70 hover:text-ink',
              rail ? 'h-11 justify-center' : 'gap-3 px-3 py-2.5',
            )}
          >
            <LogOut size={18} strokeWidth={1.9} aria-hidden />
            {!rail && 'Sign out'}
          </button>
        </div>
      )}
    </aside>
  );
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const { range, setDays, children: kids, data, selectChild } = useChild();
  return (
    <div className="no-print mb-6 flex flex-wrap items-center gap-3">
      <button className="rounded-full bg-card p-2.5 text-ink lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu size={18} />
      </button>
      {kids.length > 1 && data && (
        <div className="flex items-center gap-1 rounded-full bg-card p-1" role="group" aria-label="Switch child">
          {kids.map((k, i) => {
            const on = k.student_code === data.child.student_code;
            return (
              <button
                key={k.student_code}
                onClick={() => selectChild(k.student_code)}
                aria-pressed={on}
                title={`${k.name}, ${k.year_group}`}
                className={clsx(
                  'flex items-center gap-2 rounded-full p-1 text-[13px] font-extrabold transition-colors',
                  on ? 'bg-cream pr-3 text-ink' : 'text-ink-soft hover:bg-cream',
                )}
              >
                <span className={clsx('flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-black', childLook(i).avatar, !on && 'opacity-70')}>
                  {initials(k.name, kids.map((x) => x.name))}
                </span>
                {on && k.name.split(' ')[0]}
              </button>
            );
          })}
        </div>
      )}
      <div className="ml-auto flex flex-wrap items-center gap-2">
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
  const [collapsed, setCollapsed] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (needsLogin) router.replace('/login');
  }, [needsLogin, router]);

  useEffect(() => {
    try { setCollapsed(localStorage.getItem(COLLAPSE_KEY) === '1'); } catch { /* keep expanded */ }
  }, []);

  const toggle = () => {
    setCollapsed((c) => {
      try { localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1'); } catch { /* not remembered */ }
      return !c;
    });
  };

  return (
    <div className="min-h-screen overflow-x-hidden">
      <Sidebar open={menu} onClose={() => setMenu(false)} collapsed={collapsed} onToggle={toggle} />
      {menu && <div className="fixed inset-0 z-20 bg-ink/30 lg:hidden" onClick={() => setMenu(false)} />}
      <main className={clsx('print-full px-4 py-6 transition-[margin] duration-200 sm:px-8', collapsed ? 'lg:ml-[76px]' : 'lg:ml-[248px]')}>
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
