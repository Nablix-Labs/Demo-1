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
import { ArrowRight, Mail, Phone } from 'lucide-react';
import { useAuthStore, accessDecision, type SsoProvider, type Role } from '@/store/useAuthStore';
import { login, LoginError } from '@/lib/auth/authApi';
import { useNumeraStore } from '@/store/useNumeraStore';
import { landingRoute } from '@/lib/usePhaseRouting';
import { phasesToUnlock } from '@/lib/flow';
import { SSO_LOGO } from '@/components/auth/SsoLogos';
import BrandPanel from '@/components/auth/BrandPanel';

const SSO: { id: SsoProvider; label: string }[] = [
  { id: 'google', label: 'Google' },
  { id: 'microsoft', label: 'Microsoft' },
  { id: 'apple', label: 'Apple' },
  { id: 'school', label: 'School ID' },
];

export default function LoginPage() {
  const router = useRouter();
  const [hydrated, setHydrated] = useState(false);
  const [loginMode, setLoginMode] = useState<'email' | 'phone'>('email');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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

  // Real email/password login against the Nablix platform (POST /auth/login).
  const doLogin = async () => {
    setError(null);
    if (!/.+@.+\..+/.test(email.trim())) { setError('Please enter a valid email.'); return; }
    if (!password) { setError('Please enter your password.'); return; }
    setSubmitting(true);
    try {
      const res = await login(email.trim(), password);
      const role: Role = res.role === 'parent_guardian' ? 'parent_guardian' : 'student';
      useAuthStore.getState().loginSuccess({ token: res.access_token, role, tier: res.tier, email: email.trim(), studentCode: res.student_code });
      // Land on the phase the backend says this student is in — for a new
      // student that's the topic diagnostic, not the guided lesson.
      const store = useNumeraStore.getState();
      const { href, unlock } = landingRoute(
        res.last_journey_state?.current_phase,
        store.currentTopicId,
      );
      phasesToUnlock(unlock).forEach(store.completePhase);
      router.push(href);
    } catch (e) {
      setError(e instanceof LoginError ? e.message : 'Could not log you in. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Email uses the real endpoint; phone-OTP has no endpoint yet, so it stays on
  // the mock path.
  const onSubmit = () => (loginMode === 'email' ? void doLogin() : proceed());

  return (
    <main
      className="flex-1 min-w-0 bg-white p-3 text-ink antialiased"
      aria-label="Log in to Numera"
    >
      <div className="grid min-h-[calc(100vh-1.5rem)] gap-3 lg:grid-cols-[1.05fr_0.95fr]">
        {/* ── Form ─────────────────────────────────────────────────────── */}
        <div className="flex items-center rounded-xl border border-muted-gray bg-white px-6 py-12 sm:px-10 lg:px-14 xl:px-20">
          <div className="mx-auto w-full max-w-[460px]">
            {/* Wordmark — carries the panel's identity on small screens where
                the brand side is hidden. */}
            <div className="flex items-center gap-2.5 lg:hidden mb-10">
              <span className="w-9 h-9 rounded-lg bg-learning-blue text-white flex items-center justify-center font-bold text-base">N</span>
              <div className="leading-none">
                <div className="text-[15px] font-semibold text-ink tracking-[0.2px]">Numera</div>
                <div className="text-[8.5px] text-slate-blue tracking-[1.5px] uppercase mt-0.5">by Nablix</div>
              </div>
            </div>

            <h1 className="text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-4xl lg:text-[42px] lg:leading-[1.05]">
              Welcome back
            </h1>
            <p className="mt-3 text-lg leading-snug text-slate-blue sm:text-xl">
              Pick up where you left off.
            </p>

            <div className="mt-10 grid gap-3 sm:grid-cols-2">
              {SSO.map((p) => {
                const Logo = SSO_LOGO[p.id];
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={proceed}
                    disabled={!hydrated}
                    className="flex h-11 items-center justify-center gap-2 rounded-[10px] border border-muted-gray bg-white px-3 text-[13.5px] font-medium text-ink transition-colors hover:bg-reading-surface disabled:opacity-40"
                  >
                    <Logo size={17} />
                    <span className="whitespace-nowrap">{p.label}</span>
                  </button>
                );
              })}
            </div>

            <div className="my-8 flex items-center gap-3">
              <span className="h-px flex-1 bg-muted-gray" />
              <span className="text-[13px] font-medium text-slate-blue">or</span>
              <span className="h-px flex-1 bg-muted-gray" />
            </div>

            {/* A real <form>. Without one, Enter in the email or password field
                did nothing — there was no submit target, so the only way in was
                clicking the button (reported 2026-07-28). It also stops the
                browser warning that the password field isn't in a form, which
                is what password managers key off. */}
            <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }} noValidate>
              <div className="grid grid-cols-2 gap-1 rounded-[10px] bg-reading-surface p-1">
                {([
                  { id: 'email', label: 'Email', Icon: Mail },
                  { id: 'phone', label: 'Phone OTP', Icon: Phone },
                ] as const).map(({ id, label, Icon }) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setLoginMode(id)}
                    className={
                      'flex items-center justify-center gap-1.5 rounded-[8px] py-2 text-[12.5px] font-semibold transition-colors ' +
                      (loginMode === id ? 'bg-white text-ink shadow-sm' : 'text-slate-blue hover:text-ink')
                    }
                  >
                    <Icon size={13} />
                    {label}
                  </button>
                ))}
              </div>

              {loginMode === 'phone' ? (
                <label className="mt-5 block">
                  <span className="text-[13px] font-medium text-ink">Phone</span>
                  <div className="mt-2 flex h-14 items-center gap-2 rounded-[10px] border border-muted-gray bg-white px-4 focus-within:border-learning-blue transition-colors">
                    <Phone size={16} className="text-slate-blue flex-shrink-0" />
                    <input
                      type="tel"
                      name="tel"
                      autoComplete="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+44 7700 900000"
                      className="min-w-0 flex-1 bg-transparent text-[16px] text-ink placeholder:text-slate-blue/60 focus:outline-none"
                    />
                  </div>
                  <span className="mt-2 block text-[12.5px] text-slate-blue">
                    We&rsquo;ll text a one-time code to sign you in.
                  </span>
                </label>
              ) : (
                <>
                  <label className="mt-5 block">
                    <span className="text-[13px] font-medium text-ink">Email</span>
                    <div className="mt-2 flex h-14 items-center gap-2 rounded-[10px] border border-muted-gray bg-white px-4 focus-within:border-learning-blue transition-colors">
                      <Mail size={16} className="text-slate-blue flex-shrink-0" />
                      <input
                        type="email"
                        name="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        className="min-w-0 flex-1 bg-transparent text-[16px] text-ink placeholder:text-slate-blue/60 focus:outline-none"
                      />
                    </div>
                  </label>

                  <label className="mt-4 block">
                    <span className="flex items-center justify-between">
                      <span className="text-[13px] font-medium text-ink">Password</span>
                      <button type="button" className="text-[12px] font-medium text-learning-blue hover:underline">
                        Forgot?
                      </button>
                    </span>
                    <input
                      type="password"
                      name="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="mt-2 h-14 w-full rounded-[10px] border border-muted-gray bg-white px-4 text-[16px] text-ink placeholder:text-muted-gray focus:border-learning-blue focus:outline-none transition-colors"
                    />
                  </label>
                </>
              )}

              {error && (
                <p role="alert" className="mt-4 rounded-[10px] border border-action-orange/25 bg-action-orange/10 px-3 py-2 text-[12.5px] text-action-orange">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={!hydrated || submitting}
                className="mt-7 flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-learning-blue text-[16px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {submitting ? 'Logging in…' : <>Log in <ArrowRight size={17} /></>}
              </button>
            </form>

            <p className="mt-7 text-center text-[13px] text-slate-blue">
              New to Numera?{' '}
              <button onClick={() => router.push('/onboard')} className="font-semibold text-learning-blue hover:underline">
                Create an account
              </button>
            </p>
          </div>
        </div>

        <BrandPanel headline="Maths that meets you where you are." />
      </div>
    </main>
  );
}
