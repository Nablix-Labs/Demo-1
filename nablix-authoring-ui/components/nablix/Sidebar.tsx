'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Library,
  BookOpen,
  Target,
  HelpCircle,
  Lightbulb,
  AlertOctagon,
  Eye,
  Layers,
  ClipboardCheck,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const NAV = [
  { href: '/', label: 'Dashboard', Icon: LayoutDashboard },
  { href: '/curriculum', label: 'Curriculum', Icon: Library },
  { href: '/topics', label: 'Topics', Icon: BookOpen },
  { href: '/micro-skills', label: 'Micro-skills', Icon: Target },
  { href: '/questions', label: 'Questions', Icon: HelpCircle },
  { href: '/hints', label: 'Hints', Icon: Lightbulb },
  { href: '/misconceptions', label: 'Misconceptions', Icon: AlertOctagon },
  { href: '/visual-cues', label: 'Visual Cues', Icon: Eye },
  { href: '/scaffolds', label: 'Scaffolds', Icon: Layers },
  { href: '/review', label: 'Review', Icon: ClipboardCheck },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // Persist the collapsed choice across reloads.
  useEffect(() => {
    setCollapsed(localStorage.getItem('nbx-sidebar-collapsed') === '1');
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem('nbx-sidebar-collapsed', next ? '1' : '0');
      return next;
    });
  };

  const Item = ({ href, label, Icon }: (typeof NAV)[number]) => {
    const active = href === '/' ? pathname === '/' : pathname.startsWith(href);
    return (
      <Link
        key={href}
        href={href}
        title={collapsed ? label : undefined}
        className={cn(
          'group flex items-center rounded-[12px] text-[14px] font-semibold transition-all',
          collapsed ? 'h-11 w-11 justify-center' : 'gap-3 px-3 py-2.5',
          active
            ? 'bg-lime text-focus-navy shadow-[0_4px_16px_rgba(203,242,74,0.35)]'
            : 'text-white/80 hover:bg-white/10 hover:text-white',
        )}
      >
        <Icon className={cn('h-[20px] w-[20px] shrink-0', active ? 'text-focus-navy' : 'text-white/65 group-hover:text-white')} strokeWidth={2} />
        {!collapsed && label}
      </Link>
    );
  };

  return (
    <aside
      className={cn(
        'lg-glass-dark relative z-20 flex shrink-0 flex-col rounded-none transition-[width] duration-200',
        collapsed ? 'w-[76px]' : 'w-[240px]',
      )}
    >
      {/* Brand */}
      <div className={cn('flex items-center py-5', collapsed ? 'justify-center px-0' : 'gap-2.5 px-5')}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-lime text-base font-black text-focus-navy shadow-[0_4px_14px_rgba(203,242,74,0.45)]">
          N
        </div>
        {!collapsed && (
          <div className="leading-tight">
            <div className="font-display text-[17px] font-extrabold tracking-tight text-white">Nablix</div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-white/55">Authoring</div>
          </div>
        )}
      </div>

      <nav className={cn('lg-scroll flex-1 space-y-1 overflow-y-auto overflow-x-hidden py-2', collapsed ? 'px-3' : 'px-3')}>
        {NAV.map((n) => (
          <Item key={n.href} {...n} />
        ))}
      </nav>

      <div className="space-y-1 border-t border-white/10 px-3 py-3">
        <Link
          href="/settings"
          title={collapsed ? 'Settings' : undefined}
          className={cn(
            'group flex items-center rounded-[12px] text-[14px] font-semibold text-white/80 transition-all hover:bg-white/10 hover:text-white',
            collapsed ? 'h-11 w-11 justify-center' : 'gap-3 px-3 py-2.5',
          )}
        >
          <Settings className="h-[20px] w-[20px] shrink-0 text-white/65 group-hover:text-white" strokeWidth={2} />
          {!collapsed && 'Settings'}
        </Link>
        <button
          onClick={toggle}
          title={collapsed ? 'Expand' : 'Collapse'}
          className={cn(
            'group flex w-full items-center rounded-[12px] text-[14px] font-semibold text-white/60 transition-all hover:bg-white/10 hover:text-white',
            collapsed ? 'h-11 w-11 justify-center' : 'gap-3 px-3 py-2.5',
          )}
        >
          {collapsed ? <PanelLeftOpen className="h-[20px] w-[20px] shrink-0" strokeWidth={2} /> : <PanelLeftClose className="h-[20px] w-[20px] shrink-0" strokeWidth={2} />}
          {!collapsed && 'Collapse'}
        </button>
      </div>
    </aside>
  );
}
