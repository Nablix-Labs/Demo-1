'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Pencil, BookOpen, Target, Users, Swords, Folder, Flag, Zap,
  Bell, Clock, Headphones,
} from 'lucide-react';
import { cn } from '@/lib/cn';

const TOP_ITEMS = [
  { icon: Pencil,   label: 'Lesson',         href: '/', supportId: 'open-canvas' },
  { icon: BookOpen, label: 'Workbook',       href: '/workbook' },
  { icon: Target,   label: 'Practice',       href: '/practice' },
  { icon: Swords,   label: 'Group Challenge',href: '/challenge' },
  { icon: Zap,      label: 'Key Notes',      href: '/keynotes' },
  { icon: Users,    label: 'People',         href: '/people' },
  { icon: Folder,   label: 'Files',          href: '/files' },
  { icon: Flag,     label: 'Flagged',        href: '/flagged' },
];

const BOTTOM_ITEMS = [
  { icon: Bell,       label: 'Notifications', href: '/notifications' },
  { icon: Clock,      label: 'History',       href: '/history' },
  { icon: Headphones, label: 'Help & support',href: '/help' },
];

function RailLink({
  icon: Icon, label, href, active, supportId,
}: {
  icon: typeof Pencil; label: string; href: string; active: boolean; supportId?: string;
}) {
  return (
    <Link
      href={href}
      title={label}
      aria-label={label}
      aria-current={active ? 'page' : undefined}
      data-support-id={supportId}
      className={cn(
        'w-[38px] h-[38px] rounded-lg flex items-center justify-center transition-colors flex-shrink-0',
        active
          ? 'bg-white text-focus-navy'
          : 'bg-transparent text-white/55 hover:bg-white/10 hover:text-white'
      )}
    >
      <Icon size={18} strokeWidth={1.6} />
    </Link>
  );
}

export default function ToolRail() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <nav
      className="lg-glass-dark flex flex-col items-center flex-shrink-0 w-14 py-3.5 gap-1 m-2 rounded-2xl"
      aria-label="Tool rail"
    >
      {/* Brand mark */}
      <Link
        href="/"
        title="Numera"
        aria-label="Numera home"
        className="w-[34px] h-[34px] rounded-lg bg-ai-cyan text-white flex items-center justify-center font-bold text-base mb-2 flex-shrink-0"
      >
        N
      </Link>

      {/* Top nav */}
      {TOP_ITEMS.map((item) => (
        <RailLink key={item.href} {...item} active={isActive(item.href)} />
      ))}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Bottom nav */}
      {BOTTOM_ITEMS.map((item) => (
        <RailLink key={item.href} {...item} active={isActive(item.href)} />
      ))}
    </nav>
  );
}
