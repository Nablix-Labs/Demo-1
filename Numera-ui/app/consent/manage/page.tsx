'use client';

/**
 * Guardian consent management (§10 "Change consent → guardian flow required",
 * §11 /consent/withdraw). A student can never change consent; this screen is a
 * guardian-verified flow to review, withdraw and re-grant each consent.
 *
 * Withdrawing an account-blocking consent restricts the whole account
 * (consent_withdrawn); withdrawing a feature consent (voice/canvas) just
 * disables that feature. Mock-wired: any 6-digit code verifies the guardian.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldCheck, Check, AlertTriangle } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import {
  useAuthStore, CONSENT_PURPOSES, ACCOUNT_BLOCKING_PURPOSES, isConsentActive,
  type ConsentPurpose,
} from '@/store/useAuthStore';

export default function ManageConsentPage() {
  const router = useRouter();
  const { consents, guardian, student, accountStatus, verifyGuardian, withdrawConsent, grantConsent } = useAuthStore();
  const [phase, setPhase] = useState<'verify' | 'manage'>('verify');
  const [otp, setOtp] = useState('');
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => { void useAuthStore.persist.rehydrate(); setHydrated(true); }, []);
  useEffect(() => {
    if (hydrated && useAuthStore.getState().role === null) router.replace('/onboard');
  }, [hydrated, router]);

  const verify = () => { verifyGuardian(); setPhase('manage'); };
  const isBlocking = (p: ConsentPurpose) => ACCOUNT_BLOCKING_PURPOSES.includes(p);

  return (
    <AuthShell width={phase === 'manage' ? 560 : 440}>
      {phase === 'verify' ? (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Manage consent</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            Only a verified parent or guardian can change consent. Enter the 6-digit code
            {guardian.email ? <> sent to <span className="font-semibold text-ink">{guardian.email}</span></> : ''}.
          </p>
          <input
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            placeholder="000000"
            className="mt-6 w-full rounded-btn border border-muted-gray bg-white px-4 py-3 text-center text-[22px] tracking-[0.5em] font-semibold text-ink placeholder:text-muted-gray focus:border-ai-cyan focus:outline-none transition-colors"
          />
          <p className="text-[11px] text-slate-blue mt-2 text-center">Demo: enter any 6 digits.</p>
          <button onClick={verify} disabled={otp.length !== 6} className="btn btn-primary w-full mt-5">
            Verify <ShieldCheck size={16} />
          </button>
          <button onClick={() => router.back()} className="btn btn-secondary w-full mt-2.5">Back</button>
        </>
      ) : (
        <>
          <div className="flex items-center gap-2 text-success-sage text-[12px] font-semibold mb-2">
            <span className="w-5 h-5 rounded-full bg-success-sage text-white flex items-center justify-center">
              <Check size={12} strokeWidth={2.6} />
            </span>
            Guardian verified
          </div>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Manage consent</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            Review and change consent for {student.name || 'the student'}.
          </p>

          {accountStatus === 'consent_withdrawn' && (
            <div className="flex items-start gap-2 rounded-card border border-action-orange/30 bg-action-orange/10 px-4 py-3 mt-4">
              <AlertTriangle size={16} className="text-action-orange flex-shrink-0 mt-0.5" />
              <p className="text-[12px] text-ink leading-snug">
                A required consent is withdrawn, so learning access is currently restricted. Re-grant it to restore access.
              </p>
            </div>
          )}

          <div className="rounded-card border border-muted-gray divide-y divide-muted-gray overflow-hidden mt-4">
            {CONSENT_PURPOSES.map((p) => {
              const active = isConsentActive(consents, p.id);
              return (
                <div key={p.id} className="flex items-start gap-3 px-4 py-3">
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-ink">{p.label}</span>
                      <span
                        className={
                          'text-[9px] uppercase tracking-wide font-semibold rounded px-1.5 py-0.5 ' +
                          (active ? 'text-success-sage bg-success-sage/10' : 'text-action-orange bg-action-orange/10')
                        }
                      >
                        {active ? 'Active' : 'Withdrawn'}
                      </span>
                      {isBlocking(p.id) && (
                        <span className="text-[9px] uppercase tracking-wide font-semibold text-slate-blue bg-reading-surface rounded px-1.5 py-0.5">Required</span>
                      )}
                    </span>
                    <span className="block text-[11.5px] text-slate-blue mt-0.5 leading-snug">{p.detail}</span>
                    {isBlocking(p.id) && active && (
                      <span className="block text-[10.5px] text-action-orange mt-1">Withdrawing this restricts all learning access.</span>
                    )}
                  </span>
                  <button
                    onClick={() => (active ? withdrawConsent(p.id) : grantConsent(p.id))}
                    className={
                      'flex-shrink-0 rounded-btn border px-3 py-1.5 text-[12px] font-semibold transition-colors ' +
                      (active
                        ? 'border-muted-gray text-ink hover:border-action-orange hover:text-action-orange'
                        : 'border-focus-navy bg-focus-navy text-white hover:brightness-110')
                    }
                  >
                    {active ? 'Withdraw' : 'Re-grant'}
                  </button>
                </div>
              );
            })}
          </div>

          <button onClick={() => router.push('/')} className="btn btn-secondary w-full mt-5">Done</button>
        </>
      )}
    </AuthShell>
  );
}
