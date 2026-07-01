'use client';

/**
 * Login (§9). Authentication is only step one — after "signing in" the demo runs
 * the same access-decision chain the backend would (§13): role, account_status
 * and mandatory consent. The outcome routes the student to the app or to the
 * correct restricted screen.
 *
 * Mock-wired: credentials aren't checked; the persisted account in useAuthStore
 * stands in for a verified identity.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Mail } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import { useAuthStore, accessDecision, type SsoProvider } from '@/store/useAuthStore';

const SSO: { id: SsoProvider; label: string }[] = [
  { id: 'google', label: 'Google' },
  { id: 'microsoft', label: 'Microsoft' },
  { id: 'apple', label: 'Apple' },
  { id: 'school', label: 'School ID' },
];

export default function LoginPage() {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  useEffect(() => {
    void useAuthStore.persist.rehydrate();
    setHydrated(true);
  }, []);

  const proceed = () => {
    const s = useAuthStore.getState();
    if (s.role === null) { router.push('/onboard'); return; } // no account yet
    const outcome = accessDecision(s);
    router.push(outcome.allowed ? '/' : outcome.redirect);
  };

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold text-ink leading-tight">Welcome back</h1>
      <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
        Log in to continue learning with Numera.
      </p>

      <div className="grid grid-cols-2 gap-2.5 mt-6">
        {SSO.map((p) => (
          <button
            key={p.id}
            onClick={proceed}
            disabled={!hydrated}
            className="flex items-center justify-center gap-2 rounded-btn border border-muted-gray bg-white px-4 py-3 text-[13px] font-semibold text-ink hover:bg-reading-surface hover:border-slate-blue transition-colors"
          >
            <span className="w-5 h-5 rounded-md bg-focus-navy text-white text-[11px] font-bold flex items-center justify-center">
              {p.label[0]}
            </span>
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3 my-5">
        <span className="h-px flex-1 bg-muted-gray" />
        <span className="text-[11px] uppercase tracking-widest text-slate-blue">or with email</span>
        <span className="h-px flex-1 bg-muted-gray" />
      </div>

      <label className="block text-[12px] font-semibold text-ink">
        Email
        <div className="mt-1.5 flex items-center gap-2 rounded-btn border border-muted-gray bg-white px-3 focus-within:border-ai-cyan transition-colors">
          <Mail size={16} className="text-slate-blue flex-shrink-0" />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="flex-1 min-w-0 bg-transparent py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:outline-none"
          />
        </div>
      </label>
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        className="mt-3 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
      />

      <button onClick={proceed} disabled={!hydrated} className="btn btn-primary w-full mt-5">
        Log in <ArrowRight size={16} />
      </button>

      <p className="text-[12px] text-slate-blue text-center mt-4">
        New to Numera?{' '}
        <button onClick={() => router.push('/onboard')} className="font-semibold text-learning-blue hover:underline">
          Create an account
        </button>
      </p>
    </AuthShell>
  );
}
