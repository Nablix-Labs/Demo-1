import PageShell, { IconBadge } from '@/components/PageShell';
import { CalendarClock, MessageSquare, Trophy, FileCheck2 } from 'lucide-react';
import { cn } from '@/lib/cn';

interface Note {
  icon: typeof CalendarClock;
  title: string;
  body: string;
  when: string;
  unread: boolean;
}

const NOTES: Note[] = [
  { icon: CalendarClock, title: 'Session reminder', body: 'Your next tutoring session starts in 30 minutes.', when: '25 min ago', unread: true },
  { icon: MessageSquare, title: 'Message from Ms Sharma', body: '“Great progress on linear equations — keep it up!”', when: '2 h ago', unread: true },
  { icon: Trophy, title: 'Unit mastered', body: 'You completed all exercises in Linear Equations.', when: 'Yesterday', unread: false },
  { icon: FileCheck2, title: 'Worksheet marked', body: 'Fractions practice has been reviewed. 7 / 9 correct.', when: '2 days ago', unread: false },
];

export default function NotificationsPage() {
  const unread = NOTES.filter((n) => n.unread).length;
  return (
    <PageShell
      title="Notifications"
      subtitle={unread > 0 ? `${unread} unread` : 'You’re all caught up.'}
    >
      <div className="flex flex-col gap-2.5 max-w-2xl">
        {NOTES.map((n) => {
          const Icon = n.icon;
          return (
            <div
              key={n.title}
              className={cn(
                'flex items-start gap-4 rounded-lg border bg-white px-5 py-4 transition-colors',
                n.unread ? 'border-[#c8c8c8] border-l-[3px] border-l-[#1a1a1a]' : 'border-[#eaeaea]'
              )}
            >
              <IconBadge>
                <Icon size={18} strokeWidth={1.5} />
              </IconBadge>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[13px] font-semibold text-[#1a1a1a]">{n.title}</span>
                  {n.unread && <span className="w-1.5 h-1.5 rounded-full bg-[#1a1a1a]" />}
                </div>
                <p className="text-[12.5px] text-[#7a7a7a] mt-0.5 leading-snug">{n.body}</p>
              </div>
              <span className="flex-shrink-0 text-[11px] text-[#9a9a9a] whitespace-nowrap">{n.when}</span>
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}
