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
import { ArrowRight, Mail, Check } from 'lucide-react';
import { useAuthStore, accessDecision, type SsoProvider } from '@/store/useAuthStore';
import { SSO_LOGO } from '@/components/auth/SsoLogos';

const SSO: { id: SsoProvider; label: string }[] = [
  { id: 'google', label: 'Google' },
  { id: 'microsoft', label: 'Microsoft' },
  { id: 'apple', label: 'Apple' },
  { id: 'school', label: 'School ID' },
];

const HIGHLIGHTS = [
  'Adaptive AI tutor that meets each student at their level',
  'Guided, step-by-step maths — not just answers',
  'Safe and guardian-approved from day one',
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
    <main className="flex-1 min-w-0 flex bg-off-white" aria-label="Log in to Numera">
      {/* ── Brand hero (desktop) ─────────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col justify-between w-[46%] max-w-[620px] relative overflow-hidden bg-focus-navy text-white p-14">
        {/* depth: soft brand glows */}
        <div className="absolute -top-24 -right-16 w-80 h-80 rounded-full bg-ai-cyan/20 blur-3xl" aria-hidden />
        <div className="absolute bottom-[-6rem] left-[-4rem] w-96 h-96 rounded-full bg-learning-blue/20 blur-3xl" aria-hidden />
        {/* faint equation motif */}
        <div className="absolute inset-0 flex items-center justify-center opacity-[0.06] select-none pointer-events-none" aria-hidden>
          <span className="text-[220px] font-serif italic leading-none">∑</span>
        </div>

        <div className="relative flex items-center gap-2.5">
          <span className="w-10 h-10 rounded-xl bg-ai-cyan text-white flex items-center justify-center font-bold text-lg">N</span>
          <div className="leading-none">
            <div className="text-[17px] font-semibold tracking-[0.2px]">Numera</div>
            <div className="text-[9px] font-normal text-white/60 tracking-[2px] uppercase mt-1">by Nablix</div>
          </div>
        </div>

        <div className="relative">
          <h2 className="text-[34px] font-semibold leading-[1.15] tracking-[-0.5px]">
            Maths that meets<br />every student<br />where they are.
          </h2>
          <ul className="mt-8 flex flex-col gap-3.5">
            {HIGHLIGHTS.map((h) => (
              <li key={h} className="flex items-start gap-3 text-[13.5px] text-white/85 leading-snug">
                <span className="flex-shrink-0 mt-0.5 w-5 h-5 rounded-full bg-ai-cyan/20 text-ai-cyan flex items-center justify-center">
                  <Check size={12} strokeWidth={3} />
                </span>
                {h}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative flex items-center gap-2 text-[12px] text-white/55">
          <span className="w-1.5 h-1.5 rounded-full bg-success-sage inline-block" />
          Trusted for KS3–KS4 maths tutoring
        </div>
      </aside>

      {/* ── Login form ───────────────────────────────────────────────── */}
      <section className="flex-1 flex flex-col items-center justify-center px-6 py-10 overflow-y-auto">
        <div className="w-[400px] max-w-full">
          {/* logo shown when hero is hidden */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="w-9 h-9 rounded-lg bg-ai-cyan text-white flex items-center justify-center font-bold text-base">N</span>
            <div className="leading-none">
              <div className="text-[15px] font-semibold text-ink tracking-[0.2px]">Numera</div>
              <div className="text-[8.5px] font-normal text-slate-blue tracking-[1.5px] uppercase mt-0.5">by Nablix</div>
            </div>
          </div>

          <h1 className="text-[28px] font-semibold text-ink leading-tight tracking-[-0.3px]">Welcome back</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            Log in to continue learning with Numera.
          </p>

          <div className="flex flex-col gap-2.5 mt-7">
            {SSO.map((p) => {
              const Logo = SSO_LOGO[p.id];
              return (
                <button
                  key={p.id}
                  onClick={proceed}
                  disabled={!hydrated}
                  className="group flex items-center gap-3 rounded-btn border border-muted-gray bg-white px-4 py-3 text-[13.5px] font-semibold text-ink hover:border-slate-blue hover:shadow-sm transition-all"
                >
                  <Logo size={18} />
                  <span>Continue with {p.label}</span>
                  <ArrowRight size={15} className="ml-auto text-muted-gray group-hover:text-slate-blue transition-colors" />
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3 my-5">
            <span className="h-px flex-1 bg-muted-gray" />
            <span className="text-[11px] uppercase tracking-widest text-slate-blue">or with email</span>
            <span className="h-px flex-1 bg-muted-gray" />
          </div>

          <label className="block text-[12px] font-semibold text-ink">
            Email
            <div className="mt-1.5 flex items-center gap-2 rounded-btn border border-muted-gray bg-white px-3 focus-within:border-ai-cyan focus-within:ring-2 focus-within:ring-ai-cyan/15 transition-all">
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

          <label className="block text-[12px] font-semibold text-ink mt-3">
            <span className="flex items-center justify-between">
              Password
              <button type="button" className="text-[11px] font-medium text-learning-blue hover:underline">Forgot?</button>
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-muted-gray focus:border-ai-cyan focus:ring-2 focus:ring-ai-cyan/15 focus:outline-none transition-all"
            />
          </label>

          <button onClick={proceed} disabled={!hydrated} className="btn btn-primary w-full mt-5">
            Log in <ArrowRight size={16} />
          </button>

          <p className="text-[12px] text-slate-blue text-center mt-6">
            New to Numera?{' '}
            <button onClick={() => router.push('/onboard')} className="font-semibold text-learning-blue hover:underline">
              Create an account
            </button>
          </p>
        </div>
      </section>
    </main>
  );
}
