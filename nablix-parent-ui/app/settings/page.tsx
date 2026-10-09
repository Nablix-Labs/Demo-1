'use client';

import { useEffect, useState } from 'react';
import { Bell, Users, UserRound } from 'lucide-react';
import clsx from 'clsx';
import Shell from '@/components/Shell';
import { Card, PageHeader } from '@/components/ui';
import { signedInEmail, isSample } from '@/lib/api';
import { useChild } from '@/lib/useChild';
import type { ChildData } from '@/lib/types';

export default function SettingsPage() {
  return <Shell>{(d) => <Settings d={d} />}</Shell>;
}

const PREFS_KEY = 'nablix.parent.notifications';

const NOTIFY = [
  { id: 'weekly', label: 'Weekly summary email', detail: 'Every Sunday: score, topics and next steps.' },
  { id: 'mastered', label: 'Topic mastered', detail: 'When your child finishes a topic.' },
  { id: 'inactive', label: 'No practice for 3 days', detail: 'A gentle reminder if sessions stop.' },
  { id: 'help', label: 'Tutor needed to step in a lot', detail: 'When a session needed a lot of help.' },
] as const;

type Prefs = Record<(typeof NOTIFY)[number]['id'], boolean>;
const DEFAULTS: Prefs = { weekly: true, mastered: true, inactive: false, help: false };

function Settings({ d }: { d: ChildData }) {
  const { children: kids } = useChild();
  const [prefs, setPrefs] = useState<Prefs>(DEFAULTS);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null');
      if (saved) setPrefs({ ...DEFAULTS, ...saved });
    } catch { /* keep defaults */ }
  }, []);

  const toggle = (id: keyof Prefs) => {
    const next = { ...prefs, [id]: !prefs[id] };
    setPrefs(next);
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch { /* not saved */ }
  };

  return (
    <>
      <PageHeader title="Settings" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Notifications" icon={<Bell size={18} />} className="lg:row-span-2">
          <ul className="flex flex-col divide-y divide-line">
            {NOTIFY.map((n) => (
              <li key={n.id} className="flex items-center justify-between gap-4 py-3.5">
                <span>
                  <span className="block text-[13.5px] font-extrabold text-ink">{n.label}</span>
                  <span className="mt-0.5 block text-[12.5px] text-ink-soft">{n.detail}</span>
                </span>
                <button
                  role="switch"
                  aria-checked={prefs[n.id]}
                  aria-label={n.label}
                  onClick={() => toggle(n.id)}
                  className={clsx('relative h-6 w-11 flex-shrink-0 rounded-full transition-colors', prefs[n.id] ? 'bg-teal' : 'bg-line')}
                >
                  <span className={clsx('absolute top-0.5 h-5 w-5 rounded-full bg-card shadow transition-transform', prefs[n.id] ? 'translate-x-[22px]' : 'translate-x-0.5')} />
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[12px] text-ink-soft">
            Saved in this browser for now. Emails start once parent accounts are connected to Numera.
          </p>
        </Card>

        <Card title="Children" icon={<Users size={18} />}>
          <ul className="flex flex-col gap-2">
            {(kids.length ? kids : [d.child]).map((k) => (
              <li key={k.student_code} className="flex items-center justify-between rounded-[18px] bg-cream-deep px-3 py-2.5 text-[13px]">
                <span className="font-extrabold text-ink">{k.name}</span>
                <span className="text-ink-soft">{k.year_group}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[12px] text-ink-soft">
            A child is linked when you give consent during their sign-up. To link another child, use the same email when they sign up.
          </p>
        </Card>

        <Card title="Account" icon={<UserRound size={18} />}>
          <dl className="text-[13px]">
            <dt className="text-ink-soft">Signed in as</dt>
            <dd className="mt-0.5 font-extrabold text-ink">{isSample ? 'Sample preview (not signed in)' : signedInEmail() ?? '—'}</dd>
          </dl>
          <p className="mt-3 text-[12px] text-ink-soft">
            Need help? Email <a className="font-extrabold text-teal-deep" href="mailto:support@nablix.ai">support@nablix.ai</a>.
          </p>
        </Card>
      </div>
    </>
  );
}
