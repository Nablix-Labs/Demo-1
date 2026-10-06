'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { LogIn } from 'lucide-react';
import { signIn } from '@/lib/auth';

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only a path inside the portal — never an absolute URL from the query.
  const next = params.get('next');
  const target = next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/login') ? next : '/';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.replace(target);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.');
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="sheet w-full max-w-[400px] space-y-4 p-7">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-blue">Nablix</p>
        <h1 className="mt-1 text-2xl font-bold text-ink">Content Approver Portal</h1>
        <p className="mt-1 text-sm text-slate-blue">Sign in with your approver account.</p>
      </div>
      <div>
        <label className="label" htmlFor="email">Email</label>
        <input
          id="email" type="email" autoComplete="username" required
          className="field" value={email} onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div>
        <label className="label" htmlFor="password">Password</label>
        <input
          id="password" type="password" autoComplete="current-password" required
          className="field" value={password} onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      {error && (
        <p role="alert" className="rounded-btn bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}
      <button type="submit" className="btn btn-primary w-full" disabled={busy}>
        <LogIn className="h-4 w-4" /> {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="relative z-10 flex min-h-screen items-center justify-center p-6">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
