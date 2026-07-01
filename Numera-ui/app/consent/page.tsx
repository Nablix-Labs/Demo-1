'use client';

/**
 * Guardian consent (§7 + §8). Three phases:
 *   1. details  — capture guardian identity
 *   2. verify   — guardian confirms contact by OTP (identity only, NOT consent)
 *   3. consent  — purpose-wise consent records + safety-disclosure acknowledgement
 *
 * On accept: purpose-wise consent is recorded, the disclosure is acknowledged,
 * and the account moves to `active`. Only then is the student let into the app.
 * Mock-wired: any 6-digit code verifies (demo hint: 000000).
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Check, ShieldCheck, Lock } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import {
  useAuthStore, CONSENT_PURPOSES, MANDATORY_PURPOSES, SAFETY_DISCLOSURE_VERSION,
  type ConsentPurpose,
} from '@/store/useAuthStore';

const RELATIONSHIPS = ['Parent', 'Guardian', 'Carer'];

export default function ConsentPage() {
  const router = useRouter();
  const {
    student, accountStatus, guardian,
    setGuardian, verifyGuardian, acceptConsents, acknowledgeDisclosure, activateAccount,
  } = useAuthStore();

  const [phase, setPhase] = useState<'details' | 'verify' | 'consent'>('details');
  const [g, setG] = useState({ name: '', relationship: 'Parent', email: '', phone: '' });
  const [otp, setOtp] = useState('');
  const [checked, setChecked] = useState<Set<ConsentPurpose>>(new Set());
  const [disclosure, setDisclosure] = useState(false);

  // If someone lands here without registering, send them to sign-up.
  useEffect(() => {
    if (accountStatus === 'registration_started') router.replace('/onboard');
  }, [accountStatus, router]);

  const detailsReady = g.name.trim() && /.+@.+\..+/.test(g.email.trim());
  const sendCode = () => { setGuardian(g); setPhase('verify'); };
  const verify = () => { verifyGuardian(); setPhase('consent'); };

  const toggle = (p: ConsentPurpose) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });
  const acceptAllRequired = () => setChecked(new Set(MANDATORY_PURPOSES));

  const allMandatory = MANDATORY_PURPOSES.every((p) => checked.has(p));
  const canActivate = allMandatory && disclosure;

  const activate = () => {
    acceptConsents([...checked]);
    acknowledgeDisclosure();
    activateAccount();
    router.push('/diagnostic');
  };

  return (
    <AuthShell width={phase === 'consent' ? 560 : 480}>
      {/* Context banner */}
      <div className="flex items-center gap-2.5 rounded-btn border border-muted-gray bg-white px-4 py-3 mb-6">
        <span className="w-8 h-8 rounded-lg bg-reading-surface text-slate-blue flex items-center justify-center flex-shrink-0">
          <Lock size={15} />
        </span>
        <p className="text-[12px] text-slate-blue leading-snug">
          {student.name ? <><span className="font-semibold text-ink">{student.name}</span>&rsquo;s</> : 'The student’s'} account is
          <span className="font-semibold text-ink"> pending guardian consent</span>.
        </p>
      </div>

      {phase === 'details' && (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Parent / guardian details</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            A parent or guardian must confirm consent before learning starts.
          </p>

          <label className="block mt-6 text-[12px] font-semibold text-ink">
            Full name
            <input
              value={g.name}
              onChange={(e) => setG({ ...g, name: e.target.value })}
              placeholder="Guardian name"
              className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
            />
          </label>

          <div className="grid grid-cols-2 gap-3 mt-4">
            <label className="block text-[12px] font-semibold text-ink">
              Relationship
              <select
                value={g.relationship}
                onChange={(e) => setG({ ...g, relationship: e.target.value })}
                className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3 py-2.5 text-[14px] text-ink focus:border-ai-cyan focus:outline-none transition-colors"
              >
                {RELATIONSHIPS.map((r) => <option key={r}>{r}</option>)}
              </select>
            </label>
            <label className="block text-[12px] font-semibold text-ink">
              Phone
              <input
                value={g.phone}
                onChange={(e) => setG({ ...g, phone: e.target.value })}
                placeholder="Optional"
                className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
              />
            </label>
          </div>

          <label className="block mt-4 text-[12px] font-semibold text-ink">
            Email
            <input
              type="email"
              value={g.email}
              onChange={(e) => setG({ ...g, email: e.target.value })}
              placeholder="guardian@example.com"
              className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
            />
          </label>

          <button onClick={sendCode} disabled={!detailsReady} className="btn btn-primary w-full mt-6">
            Send verification code <ArrowRight size={16} />
          </button>
        </>
      )}

      {phase === 'verify' && (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Verify it&rsquo;s you</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            We sent a 6-digit code to <span className="font-semibold text-ink">{guardian.email}</span>. This confirms
            your contact — it isn&rsquo;t consent yet.
          </p>

          <input
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            placeholder="000000"
            className="mt-6 w-full rounded-btn border border-muted-gray bg-white px-4 py-3 text-center text-[22px] tracking-[0.5em] font-semibold text-ink placeholder:text-muted-gray focus:border-ai-cyan focus:outline-none transition-colors"
          />
          <p className="text-[11px] text-slate-blue mt-2 text-center">Demo: enter any 6 digits (e.g. 000000).</p>

          <button onClick={verify} disabled={otp.length !== 6} className="btn btn-primary w-full mt-5">
            Verify <ShieldCheck size={16} />
          </button>
          <button onClick={() => setPhase('details')} className="btn btn-secondary w-full mt-2.5">Back</button>
        </>
      )}

      {phase === 'consent' && (
        <>
          <div className="flex items-center gap-2 text-success-sage text-[12px] font-semibold mb-2">
            <span className="w-5 h-5 rounded-full bg-success-sage text-white flex items-center justify-center">
              <Check size={12} strokeWidth={2.6} />
            </span>
            Guardian verified
          </div>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Consent to get started</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            Please review and accept. Each item is stored as a separate consent record.
          </p>

          <button onClick={acceptAllRequired} className="btn btn-secondary w-full mt-5 mb-3 text-[12px]">
            Accept all required
          </button>

          <div className="rounded-card border border-muted-gray divide-y divide-muted-gray overflow-hidden">
            {CONSENT_PURPOSES.map((p) => {
              const on = checked.has(p.id);
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-reading-surface transition-colors"
                >
                  <span
                    className={
                      'flex-shrink-0 mt-0.5 w-5 h-5 rounded-md border flex items-center justify-center transition-colors ' +
                      (on ? 'bg-focus-navy border-focus-navy text-white' : 'border-muted-gray bg-white')
                    }
                  >
                    {on && <Check size={13} strokeWidth={2.6} />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-ink">{p.label}</span>
                      {p.mandatory ? (
                        <span className="text-[9px] uppercase tracking-wide font-semibold text-action-orange bg-action-orange/10 rounded px-1.5 py-0.5">Required</span>
                      ) : (
                        <span className="text-[9px] uppercase tracking-wide font-semibold text-slate-blue bg-reading-surface rounded px-1.5 py-0.5">Optional</span>
                      )}
                    </span>
                    <span className="block text-[11.5px] text-slate-blue mt-0.5 leading-snug">{p.detail}</span>
                  </span>
                </button>
              );
            })}
          </div>

          {/* Safety disclosure (§8) */}
          <button
            onClick={() => setDisclosure((d) => !d)}
            className="w-full flex items-start gap-3 rounded-card border border-muted-gray bg-reading-surface px-4 py-3 mt-3 text-left hover:border-slate-blue transition-colors"
          >
            <span
              className={
                'flex-shrink-0 mt-0.5 w-5 h-5 rounded-md border flex items-center justify-center transition-colors ' +
                (disclosure ? 'bg-focus-navy border-focus-navy text-white' : 'border-muted-gray bg-white')
              }
            >
              {disclosure && <Check size={13} strokeWidth={2.6} />}
            </span>
            <span className="min-w-0 flex-1">
              <span className="text-[13px] font-semibold text-ink">Safety &amp; AI-limitation disclosure</span>
              <span className="block text-[11.5px] text-slate-blue mt-0.5 leading-snug">
                I understand Numera is an AI tutor with English, safeguarding and emergency limitations
                ({SAFETY_DISCLOSURE_VERSION}).
              </span>
            </span>
          </button>

          <button onClick={activate} disabled={!canActivate} className="btn btn-primary w-full mt-5">
            Accept &amp; activate account <ArrowRight size={16} />
          </button>
          {!canActivate && (
            <p className="text-[11px] text-slate-blue text-center mt-2.5">
              All required consents and the disclosure must be accepted to continue.
            </p>
          )}
        </>
      )}
    </AuthShell>
  );
}
