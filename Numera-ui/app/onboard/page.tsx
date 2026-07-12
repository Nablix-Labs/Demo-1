'use client';

/**
 * Registration (§5) — creates the student identity, then holds access until
 * guardian consent. Step 1 picks an authentication method (SSO / email OTP /
 * password); step 2 captures the student profile. On finish the account is set
 * to consent_pending and the guardian is sent to /consent.
 *
 * Mock-wired: no real auth provider — SSO/OTP "succeed" immediately. Identity is
 * modelled in useAuthStore; name/age are mirrored to the main store for the
 * existing greeting + Key Stage logic.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Mail, Phone, KeyRound, ShieldCheck } from 'lucide-react';
import AuthShell from '@/components/auth/AuthShell';
import { useAuthStore, type SsoProvider, type AuthMethod } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { SSO_LOGO } from '@/components/auth/SsoLogos';

const SSO: { id: SsoProvider; label: string }[] = [
  { id: 'google', label: 'Google' },
  { id: 'microsoft', label: 'Microsoft' },
  { id: 'apple', label: 'Apple' },
  { id: 'school', label: 'School ID' },
];

const AGE_BANDS = [
  { band: '11–14 (KS3)', age: 12 },
  { band: '14–16 (KS4)', age: 15 },
];
const GRADES = ['Year 7', 'Year 8', 'Year 9', 'Year 10', 'Year 11'];
const MODES: { id: 'voice' | 'balanced' | 'text'; label: string }[] = [
  { id: 'voice', label: 'Voice' },
  { id: 'balanced', label: 'Balanced' },
  { id: 'text', label: 'Text' },
];

export default function OnboardPage() {
  const router = useRouter();
  const startRegistration = useAuthStore((s) => s.startRegistration);
  const setStudentProfile = useAuthStore((s) => s.setStudentProfile);
  const setStudentName = useNumeraStore((s) => s.setStudentName);
  const setStudentAge = useNumeraStore((s) => s.setStudentAge);

  const [step, setStep] = useState<1 | 2>(1);

  // Step 1 — auth method
  const [authMode, setAuthMode] = useState<'email_otp' | 'phone_otp' | 'password'>('email_otp');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');

  // Step 2 — student profile
  const [name, setName] = useState('');
  const [ageBand, setAgeBand] = useState(AGE_BANDS[1].band);
  const [grade, setGrade] = useState(GRADES[2]);
  const [mode, setMode] = useState<'voice' | 'balanced' | 'text'>('balanced');

  const chooseSso = (ssoProvider: SsoProvider) => {
    startRegistration('sso', { ssoProvider });
    setStep(2);
  };

  const continueEmail = () => {
    const method: AuthMethod = authMode;
    startRegistration(method, { email: email.trim(), phone: phone.trim() });
    setStep(2);
  };

  const emailValid = /.+@.+\..+/.test(email.trim());
  const phoneValid = phone.replace(/\D/g, '').length >= 7;
  const step1Ready =
    authMode === 'phone_otp'
      ? phoneValid
      : emailValid && (authMode === 'email_otp' || password.length >= 6);

  const finish = () => {
    const age = AGE_BANDS.find((a) => a.band === ageBand)?.age ?? 15;
    setStudentProfile({ name: name.trim(), ageBand, gradeBand: grade, preferredMode: mode });
    setStudentName(name.trim());
    setStudentAge(age);
    router.push('/consent');
  };

  return (
    <AuthShell step={step} totalSteps={2}>
      {step === 1 ? (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Create your account</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            Sign up to start learning. A parent or guardian will confirm consent next.
          </p>

          {/* SSO */}
          <div className="grid grid-cols-2 gap-2.5 mt-6">
            {SSO.map((p) => {
              const Logo = SSO_LOGO[p.id];
              return (
                <button
                  key={p.id}
                  onClick={() => chooseSso(p.id)}
                  className="flex items-center justify-center gap-2 rounded-btn border border-muted-gray bg-white px-4 py-3 text-[13px] font-semibold text-ink hover:bg-reading-surface hover:border-slate-blue hover:shadow-sm transition-all"
                >
                  <Logo size={17} />
                  {p.label}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3 my-5">
            <span className="h-px flex-1 bg-muted-gray" />
            <span className="text-[11px] uppercase tracking-widest text-slate-blue">or with email / phone</span>
            <span className="h-px flex-1 bg-muted-gray" />
          </div>

          {/* Method: email OTP · phone OTP · password */}
          <div className="grid grid-cols-3 gap-1 rounded-btn bg-reading-surface p-1">
            {([
              { id: 'email_otp', label: 'Email OTP', Icon: ShieldCheck },
              { id: 'phone_otp', label: 'Phone OTP', Icon: Phone },
              { id: 'password', label: 'Password', Icon: KeyRound },
            ] as const).map(({ id, label, Icon }) => (
              <button
                key={id}
                onClick={() => setAuthMode(id)}
                className={
                  'flex items-center justify-center gap-1.5 rounded-[10px] py-2 text-[12px] font-semibold transition-colors ' +
                  (authMode === id ? 'bg-white text-ink shadow-sm' : 'text-slate-blue hover:text-ink')
                }
              >
                <Icon size={13} />
                {label}
              </button>
            ))}
          </div>

          {authMode === 'phone_otp' ? (
            <label className="block mt-3 text-[12px] font-semibold text-ink">
              Phone
              <div className="mt-1.5 flex items-center gap-2 rounded-btn border border-muted-gray bg-white px-3 focus-within:border-ai-cyan transition-colors">
                <Phone size={16} className="text-slate-blue flex-shrink-0" />
                <input
                  type="tel"
                  data-support-id="registration-phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+44 7700 900000"
                  className="flex-1 min-w-0 bg-transparent py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:outline-none"
                />
              </div>
            </label>
          ) : (
            <label className="block mt-3 text-[12px] font-semibold text-ink">
              Email
              <div className="mt-1.5 flex items-center gap-2 rounded-btn border border-muted-gray bg-white px-3 focus-within:border-ai-cyan transition-colors">
                <Mail size={16} className="text-slate-blue flex-shrink-0" />
                <input
                  type="email"
                  data-support-id="registration-email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="flex-1 min-w-0 bg-transparent py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:outline-none"
                />
              </div>
            </label>
          )}

          {authMode === 'password' && (
            <input
              type="password"
              data-support-id="registration-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Create a password (min 6 chars)"
              className="mt-3 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
            />
          )}

          <button onClick={continueEmail} disabled={!step1Ready} data-support-id="registration-continue" className="btn btn-primary w-full mt-5">
            Continue <ArrowRight size={16} />
          </button>

          <p className="text-[12px] text-slate-blue text-center mt-4">
            Already have an account?{' '}
            <button onClick={() => router.push('/login')} className="font-semibold text-learning-blue hover:underline">
              Log in
            </button>
          </p>
        </>
      ) : (
        <>
          <h1 className="text-2xl font-semibold text-ink leading-tight">Tell us about the student</h1>
          <p className="text-[13px] text-slate-blue mt-1.5 leading-relaxed">
            This tailors the maths level and tutoring mode.
          </p>

          <label className="block mt-6 text-[12px] font-semibold text-ink">
            Student name
            <input
              data-support-id="registration-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="First name"
              className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3.5 py-2.5 text-[14px] text-ink placeholder:text-slate-blue focus:border-ai-cyan focus:outline-none transition-colors"
            />
          </label>

          <div className="grid grid-cols-2 gap-3 mt-4">
            <label className="block text-[12px] font-semibold text-ink">
              Age band
              <select
                data-support-id="curriculum-selector"
                value={ageBand}
                onChange={(e) => setAgeBand(e.target.value)}
                className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3 py-2.5 text-[14px] text-ink focus:border-ai-cyan focus:outline-none transition-colors"
              >
                {AGE_BANDS.map((a) => <option key={a.band}>{a.band}</option>)}
              </select>
            </label>
            <label className="block text-[12px] font-semibold text-ink">
              Year group
              <select
                data-support-id="grade-selector"
                value={grade}
                onChange={(e) => setGrade(e.target.value)}
                className="mt-1.5 w-full rounded-btn border border-muted-gray bg-white px-3 py-2.5 text-[14px] text-ink focus:border-ai-cyan focus:outline-none transition-colors"
              >
                {GRADES.map((g) => <option key={g}>{g}</option>)}
              </select>
            </label>
          </div>

          <div className="mt-4">
            <span className="text-[12px] font-semibold text-ink">Preferred tutoring mode</span>
            <div className="mt-1.5 grid grid-cols-3 gap-1 rounded-btn bg-reading-surface p-1">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setMode(m.id)}
                  className={
                    'rounded-[10px] py-2 text-[12px] font-semibold transition-colors ' +
                    (mode === m.id ? 'bg-white text-ink shadow-sm' : 'text-slate-blue hover:text-ink')
                  }
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          <button onClick={finish} disabled={name.trim().length === 0} data-support-id="registration-continue" className="btn btn-primary w-full mt-6">
            Continue to guardian consent <ArrowRight size={16} />
          </button>
          <button onClick={() => setStep(1)} data-support-id="registration-back" className="btn btn-secondary w-full mt-2.5">
            Back
          </button>
        </>
      )}
    </AuthShell>
  );
}
