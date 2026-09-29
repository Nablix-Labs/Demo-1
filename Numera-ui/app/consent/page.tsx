'use client';

/**
 * Guardian consent (§7 + §8). Three phases:
 *   1. details  — capture guardian identity
 *   2. verify   — guardian confirms contact by OTP (identity only, NOT consent)
 *   3. consent  — purpose-wise consent records + safety-disclosure acknowledgement
 *
 * On accept: purpose-wise consent is recorded, the disclosure is acknowledged,
 * and the account moves to `active`. Only then is the student let into the app.
 *
 * Every step goes through lib/auth/registrationApi (docs/ONBOARDING-API.md).
 * On the live path the accept call returns a login-shaped token, so the new
 * student is signed in without a second log-in. On the mock path any 6 digits
 * verify (demo hint: 000000) and the account is activated locally.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Check, ShieldCheck, Lock } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import {
  submitGuardian, verifyGuardianOtp, resendGuardianOtp, acceptConsents as apiAcceptConsents,
  RegistrationError, registrationLive,
} from '@/lib/auth/registrationApi';
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
  const [resent, setResent] = useState(false);
  const [checked, setChecked] = useState<Set<ConsentPurpose>>(new Set());
  const [disclosure, setDisclosure] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  /** Runs one server step, showing its error on this page instead of throwing. */
  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof RegistrationError ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  const registrationId = () => {
    const id = useAuthStore.getState().registrationId;
    if (!id) throw new RegistrationError(410, 'REGISTRATION_EXPIRED', 'This sign-up has timed out. Please start again from sign up.');
    return id;
  };
  const guardianId = () => {
    const id = useAuthStore.getState().guardianId;
    if (!id) { setPhase('details'); throw new RegistrationError(400, null, 'Please send the verification code again.'); }
    return id;
  };

  // If someone lands here without registering, send them to sign-up.
  useEffect(() => {
    if (accountStatus === 'registration_started') router.replace('/onboard');
  }, [accountStatus, router]);

  const detailsReady = g.name.trim() && /.+@.+\..+/.test(g.email.trim());
  const sendCode = () => run(async () => {
    const res = await submitGuardian({
      registration_id: registrationId(),
      name: g.name.trim(),
      relationship: g.relationship,
      email: g.email.trim(),
      phone: g.phone.trim() || null,
    });
    setGuardian(g);
    useAuthStore.getState().setRegistrationIds({ guardianId: res.guardian_id });
    setSentTo(res.otp_sent_to);
    setOtp('');
    setResent(false);
    setPhase('verify');
  });
  const verify = () => run(async () => {
    await verifyGuardianOtp(guardianId(), otp);
    verifyGuardian();
    setPhase('consent');
  });
  const resend = () => run(async () => {
    const res = await resendGuardianOtp(guardianId());
    if (res.otp_sent_to) setSentTo(res.otp_sent_to);
    setResent(true);
  });

  const toggle = (p: ConsentPurpose) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });
  const acceptAllRequired = () => setChecked(new Set(MANDATORY_PURPOSES));

  const allMandatory = MANDATORY_PURPOSES.every((p) => checked.has(p));
  const canActivate = allMandatory && disclosure;

  const activate = () => run(async () => {
    const res = await apiAcceptConsents({
      registration_id: registrationId(),
      guardian_id: guardianId(),
      accepted_purposes: Array.from(checked),
      disclosure_version: SAFETY_DISCLOSURE_VERSION,
    });
    acceptConsents(Array.from(checked));
    acknowledgeDisclosure();
    if (res) {
      // The server's account is active and this is its token: sign in with it.
      useAuthStore.getState().loginSuccess({
        token: res.access_token, role: 'student', tier: res.tier,
        email: useAuthStore.getState().email, studentCode: res.student_code,
      });
    } else if (!registrationLive()) {
      activateAccount();
    }
    useAuthStore.getState().setRegistrationIds({ registrationId: null, guardianId: null });
    router.push('/diagnostic');
  });

  const errorBox = error && (
    <p role="alert" className="mt-4 rounded-[10px] border border-action-orange/25 bg-action-orange/10 px-3 py-2 text-[12.5px] text-action-orange">
      {error}
    </p>
  );

  return (
    <AuthShell>
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

          {errorBox}

          <button onClick={sendCode} disabled={!detailsReady || busy} className="btn btn-primary w-full mt-6">
            {busy ? 'Sending…' : <>Send verification code <ArrowRight size={16} /></>}
          </button>
        </>
      )}

      {phase === 'verify' && (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Verify it&rsquo;s you</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            We sent a 6-digit code to <span className="font-semibold text-ink">{sentTo ?? guardian.email}</span>. This confirms
            your contact — it isn&rsquo;t consent yet.
          </p>

          <input
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            placeholder="000000"
            className="mt-6 w-full rounded-btn border border-muted-gray bg-white px-4 py-3 text-center text-[22px] tracking-[0.5em] font-semibold text-ink placeholder:text-muted-gray focus:border-ai-cyan focus:outline-none transition-colors"
          />
          {!registrationLive() && (
            <p className="text-[11px] text-slate-blue mt-2 text-center">Demo: enter any 6 digits (e.g. 000000).</p>
          )}

          {errorBox}

          <button onClick={verify} disabled={otp.length !== 6 || busy} className="btn btn-primary w-full mt-5">
            {busy ? 'Checking…' : <>Verify <ShieldCheck size={16} /></>}
          </button>
          <button onClick={() => { setError(null); setPhase('details'); }} className="btn btn-secondary w-full mt-2.5">Back</button>

          <p className="text-[12px] text-slate-blue text-center mt-4">
            {resent ? (
              'A new code is on its way.'
            ) : (
              <>
                Didn&rsquo;t get the code?{' '}
                <button
                  onClick={resend}
                  disabled={busy}
                  data-support-id="resend-verification"
                  className="font-semibold text-learning-blue hover:underline"
                >
                  Resend code
                </button>
              </>
            )}
          </p>
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

          {errorBox}

          <button onClick={activate} disabled={!canActivate || busy} className="btn btn-primary w-full mt-5">
            {busy ? 'Activating…' : <>Accept &amp; activate account <ArrowRight size={16} /></>}
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
