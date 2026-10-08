'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Logo } from '@/components/Shell';
import { Hero, Wave, PillButton, art } from '@/components/ui';
import { signIn, isSample } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.replace('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.');
    } finally {
      setBusy(false);
    }
  };

  const field = 'mt-1.5 w-full rounded-full bg-cream-deep px-5 py-3.5 text-[15px] font-bold text-ink outline-none ring-teal focus:ring-2';

  return (
    <main className="grid min-h-screen gap-4 p-4 lg:grid-cols-2">
      <div className="flex flex-col justify-center rounded-card bg-card px-6 py-12 sm:px-14">
        <Logo />
        <h1 className="mt-10 text-[38px] font-black leading-[1.05] tracking-[-0.03em] text-ink">Your child&apos;s maths, made clear.</h1>
        <p className="mt-3 max-w-md text-[15px] font-bold text-ink-soft">Progress, strengths and what comes next. All in one place.</p>

        {isSample ? (
          <div className="mt-8 max-w-md rounded-[22px] bg-mustard-soft p-5">
            <p className="text-[14px] font-bold text-ink">
              Parent sign-in opens once parent accounts are connected to Numera. Until then, explore the portal with a made-up student.
            </p>
            <PillButton href="/" className="mt-4" icon={<ArrowRight size={14} strokeWidth={2.6} />}>Open the sample dashboard</PillButton>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 flex max-w-md flex-col gap-4">
            <label className="px-1 text-[13px] font-extrabold text-ink">
              Email
              <input type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={field} />
            </label>
            <label className="px-1 text-[13px] font-extrabold text-ink">
              Password
              <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={field} />
            </label>
            {error && <p role="alert" className="rounded-[18px] bg-coral-soft px-4 py-3 text-[13.5px] font-bold text-ink">{error}</p>}
            <PillButton disabled={busy} className="w-full" icon={<ArrowRight size={14} strokeWidth={2.6} />}>{busy ? 'Signing in…' : 'Sign in'}</PillButton>
            <p className="px-1 text-[12.5px] font-bold text-ink-soft">Use the email you gave when your child signed up.</p>
          </form>
        )}
      </div>

      <Hero className="hidden min-h-[560px] flex-col justify-end lg:flex">
        <Wave className="bottom-0 h-40" color="#F4B63F" />
        {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
        <img src={art('axo-wave')} alt="" aria-hidden className="pointer-events-none absolute bottom-8 left-1/2 h-[340px] w-auto -translate-x-1/2" />
        <div className="absolute left-7 top-7 max-w-xs">
          <p className="text-[26px] font-black leading-tight">Meet the tutor your child learns with.</p>
          <p className="mt-2 text-[14px] font-bold text-white/80">Patient, step by step, and never gives the answer away.</p>
        </div>
      </Hero>
    </main>
  );
}
