'use client';

/**
 * Restricted access (§12 states + §14 messages). Shown when the access-decision
 * chain blocks a student: consent pending/withdrawn, suspended, locked or
 * deleted. Each state gets its own message and recovery route.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Lock, ShieldAlert, Clock, Ban, ArrowRight } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import { useAuthStore, type AccountStatus } from '@/store/useAuthStore';

type View = {
  Icon: typeof Lock;
  tone: 'amber' | 'orange' | 'navy';
  title: string;
  message: string;
  cta?: { label: string; href: string };
};

const VIEWS: Partial<Record<AccountStatus, View>> = {
  consent_pending: {
    Icon: Lock, tone: 'amber',
    title: 'Guardian consent required',
    message: 'Your parent or guardian consent is required before you can start learning.',
    cta: { label: 'Complete consent', href: '/consent' },
  },
  consent_withdrawn: {
    Icon: ShieldAlert, tone: 'orange',
    title: 'Access restricted',
    message: 'Access is restricted because required consent has been withdrawn.',
    cta: { label: 'Review consent', href: '/consent' },
  },
  suspended: {
    Icon: Ban, tone: 'orange',
    title: 'Account suspended',
    message: 'Your account is currently suspended. Please contact support.',
  },
  locked: {
    Icon: Clock, tone: 'navy',
    title: 'Account temporarily locked',
    message: 'Your account is locked due to a security check. Please recover access to continue.',
    cta: { label: 'Recover access', href: '/login' },
  },
  deleted: {
    Icon: Ban, tone: 'orange',
    title: 'Account unavailable',
    message: 'This account has been deleted and can no longer be accessed.',
  },
};

const TONE: Record<View['tone'], string> = {
  amber: 'bg-highlight-amber/15 text-highlight-amber',
  orange: 'bg-action-orange/15 text-action-orange',
  navy: 'bg-focus-navy/10 text-focus-navy',
};

export default function RestrictedPage() {
  const router = useRouter();
  const [status, setStatus] = useState<AccountStatus | null>(null);

  useEffect(() => {
    void useAuthStore.persist.rehydrate();
    const s = useAuthStore.getState();
    if (s.role === null || s.accountStatus === 'registration_started') { router.replace('/onboard'); return; }
    if (s.accountStatus === 'active') { router.replace('/'); return; }
    setStatus(s.accountStatus);
  }, [router]);

  const view = status ? VIEWS[status] : undefined;
  if (!view) return <AuthShell><div className="h-40" /></AuthShell>;

  const { Icon } = view;
  return (
    <AuthShell>
      <div className="text-center">
        <span className={'w-14 h-14 mx-auto rounded-2xl flex items-center justify-center mb-5 ' + TONE[view.tone]}>
          <Icon size={26} strokeWidth={1.8} />
        </span>
        <h1 className="text-2xl font-semibold text-ink leading-tight">{view.title}</h1>
        <p className="text-[13px] text-slate-blue mt-2 leading-relaxed max-w-sm mx-auto">{view.message}</p>

        {view.cta && (
          <button onClick={() => router.push(view.cta!.href)} className="btn btn-primary w-full mt-6">
            {view.cta.label} <ArrowRight size={16} />
          </button>
        )}
        <button onClick={() => router.push('/login')} className="btn btn-secondary w-full mt-2.5">
          Back to log in
        </button>
      </div>
    </AuthShell>
  );
}
