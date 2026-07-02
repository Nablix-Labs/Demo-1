'use client';

import { useState } from 'react';
import PageShell, { IconBadge } from '@/components/PageShell';
import { ChevronDown, Mail, MessageCircle, BookOpen } from 'lucide-react';
import { cn } from '@/lib/cn';

const FAQS = [
  {
    q: 'How does the voice tutor work?',
    a: 'Tap the mic in the left panel and talk through your working out loud. Numera listens, follows your reasoning, and asks guiding questions — it won’t just give you the answer.',
  },
  {
    q: 'How do I show my working?',
    a: 'Use the canvas in the centre. Pick the pen, ruler, or shape tool from the floating toolbar, write your steps, then tap Check to submit them for feedback.',
  },
  {
    q: 'Can I revisit a problem later?',
    a: 'Yes — flag any question and it’ll appear under Flagged so you can come back to it whenever you like.',
  },
  {
    q: 'Where are my saved worksheets?',
    a: 'Everything you save — worksheets, canvas snapshots and notes — lives under Files, grouped by session.',
  },
  {
    q: 'Is my camera always on?',
    a: 'The student camera is a placeholder in this build. When enabled, you can turn it off any time; audio and video are only used during an active session.',
  },
];

const CONTACTS = [
  { icon: MessageCircle, title: 'Chat with support', detail: 'Typical reply in a few minutes' },
  { icon: Mail, title: 'Email us', detail: 'support@nablix.com' },
  { icon: BookOpen, title: 'Browse guides', detail: 'Step-by-step help articles' },
];

export default function HelpPage() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <PageShell
      title="Help & support"
      subtitle="Answers to common questions, or reach a human."
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 max-w-5xl">
        {/* FAQ */}
        <div className="lg:col-span-2">
          <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-3">
            Frequently asked
          </div>
          <div className="rounded-lg border border-muted-gray divide-y divide-muted-gray overflow-hidden">
            {FAQS.map((f, i) => {
              const isOpen = open === i;
              return (
                <div key={i}>
                  <button
                    onClick={() => setOpen(isOpen ? null : i)}
                    aria-expanded={isOpen}
                    className="w-full flex items-center justify-between gap-4 px-5 py-4 text-left hover:bg-reading-surface transition-colors"
                  >
                    <span className="text-[13.5px] font-semibold text-ink">{f.q}</span>
                    <ChevronDown
                      size={18}
                      strokeWidth={1.6}
                      className={cn('flex-shrink-0 text-slate-blue transition-transform', isOpen && 'rotate-180')}
                    />
                  </button>
                  {isOpen && (
                    <p className="px-5 pb-4 -mt-1 text-[12.5px] text-slate-blue leading-relaxed">
                      {f.a}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Contact */}
        <div>
          <div className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue mb-3">
            Get in touch
          </div>
          <div className="flex flex-col gap-2.5">
            {CONTACTS.map((c) => {
              const Icon = c.icon;
              return (
                <button
                  key={c.title}
                  className="flex items-center gap-3.5 rounded-lg border border-muted-gray bg-white px-4 py-3.5 text-left hover:border-muted-gray transition-colors"
                >
                  <IconBadge>
                    <Icon size={18} strokeWidth={1.5} />
                  </IconBadge>
                  <div>
                    <div className="text-[13px] font-semibold text-ink">{c.title}</div>
                    <div className="text-[11.5px] text-slate-blue mt-0.5">{c.detail}</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </PageShell>
  );
}
