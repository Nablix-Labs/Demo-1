/**
 * Registration + guardian consent — the calls behind /onboard and /consent.
 *
 * The contract (docs/ONBOARDING-API.md) was written from these pages, for the
 * backend to implement. Until it exists the pages run on a local mock, so the
 * demo keeps walking the real flow; set NEXT_PUBLIC_REGISTRATION_LIVE=true to
 * send every step to the auth server instead. Both paths go through the same
 * functions, so switching over changes no page code.
 *
 * Same server, proxy and error body as POST /auth/login (lib/auth/authApi).
 */

import type { LoginResponse } from './authApi';

const AUTH_BASE = (process.env.NEXT_PUBLIC_AUTH_BASE_URL ?? '/nablix-auth').replace(/\/+$/, '');

export const registrationLive = (): boolean => process.env.NEXT_PUBLIC_REGISTRATION_LIVE === 'true';

export type RegistrationMethod = 'email_otp' | 'phone_otp' | 'password' | 'sso';

export interface StartRegistrationRequest {
  method: RegistrationMethod;
  email?: string;
  phone?: string;
  password?: string;
  sso_provider?: 'google' | 'microsoft' | 'apple' | 'school';
}

export interface StartRegistrationResponse {
  registration_id: string;
  /** False for password sign-up when the server does not verify the email first. */
  otp_required: boolean;
  /** Masked destination, for "We sent a code to m•••@example.com". */
  otp_sent_to: string | null;
  expires_in_s: number | null;
  /** SSO only: where to send the browser. It comes back to /onboard?registration_id=… */
  redirect_url?: string | null;
}

export interface OtpSentResponse {
  otp_sent_to: string | null;
  expires_in_s: number | null;
}

export interface StudentProfileRequest {
  registration_id: string;
  display_name: string;
  age_band: string;
  grade_band: string;
  preferred_mode: 'voice' | 'balanced' | 'text';
}

export interface StudentProfileResponse {
  student_id: string;
  student_code: string | null;
  account_status: 'consent_pending';
}

export interface GuardianRequest {
  registration_id: string;
  name: string;
  relationship: string;
  email: string;
  phone: string | null;
}

export interface GuardianResponse extends OtpSentResponse {
  guardian_id: string;
}

export interface AcceptConsentRequest {
  registration_id: string;
  guardian_id: string;
  accepted_purposes: string[];
  disclosure_version: string;
}

/** Same shape as the login response, so the new student is signed straight in. */
export type AcceptConsentResponse = LoginResponse & { account_status: 'active' };

/** Any failed step. `status` 0 = the request never landed. `field` names the input to mark. */
export class RegistrationError extends Error {
  status: number;
  code: string | null;
  field: string | null;
  constructor(status: number, code: string | null, message: string, field: string | null = null) {
    super(message);
    this.name = 'RegistrationError';
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

/** Student-facing copy, by the server's error_code first and the status second. */
function messageFor(status: number, code: string | null, field: string | null): string {
  switch (code) {
    case 'ACCOUNT_EXISTS': return 'An account already exists for this email or phone. Try logging in instead.';
    case 'OTP_INVALID': return "That code isn't right. Check it and try again.";
    case 'OTP_EXPIRED': return 'That code has expired. Ask for a new one.';
    case 'RATE_LIMITED': return 'Too many attempts. Please wait a minute and try again.';
    case 'REGISTRATION_EXPIRED': return 'This sign-up has timed out. Please start again.';
    case 'GUARDIAN_NOT_VERIFIED': return 'The guardian needs to verify their code first.';
    case 'MANDATORY_CONSENT_MISSING': return 'All required consents must be accepted to continue.';
    case 'VALIDATION_ERROR':
      return field ? `Please check the ${field.replace(/_/g, ' ')} and try again.` : 'Please check your details and try again.';
  }
  if (status === 0 || status === 404 || status >= 502) return "Can't reach the sign-up service right now. Please try again shortly.";
  if (status >= 500) return 'The server ran into a problem. Please try again in a moment.';
  return 'Something went wrong. Please try again.';
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${AUTH_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new RegistrationError(0, null, messageFor(0, null, null));
  }
  if (!res.ok) {
    type ErrorBody = { error_code?: string; message?: string; field?: string | null };
    const err = await res.json().then((b: unknown) => (b && typeof b === 'object' ? (b as ErrorBody) : null), () => null); // null for a proxy's HTML page
    const code = err?.error_code ?? null;
    const field = err?.field ?? null;
    console.error('[registration] failed', { path, status: res.status, body: err });
    throw new RegistrationError(res.status, code, messageFor(res.status, code, field), field);
  }
  return (await res.json()) as T;
}

// ── Mock, used until the endpoints exist ─────────────────────────────────────

const mockId = (prefix: string) => `${prefix}-mock-${Math.random().toString(36).slice(2, 10)}`;
const mask = (to: string) => to.replace(/^(.).*(@.*)$/, '$1•••$2');
/** Any 6 digits verify, as the demo pages have always said. */
const mockVerify = (code: string) => {
  if (!/^\d{6}$/.test(code)) throw new RegistrationError(400, 'OTP_INVALID', messageFor(400, 'OTP_INVALID', null));
};

// ── Calls, in flow order ─────────────────────────────────────────────────────

export async function startRegistration(req: StartRegistrationRequest): Promise<StartRegistrationResponse> {
  if (registrationLive()) return post('/auth/register/start', req);
  const otp = req.method === 'email_otp' || req.method === 'phone_otp';
  return {
    registration_id: mockId('REG'),
    otp_required: otp,
    otp_sent_to: otp ? mask(req.email || req.phone || '') : null,
    expires_in_s: otp ? 600 : null,
    redirect_url: null,
  };
}

export async function verifyRegistrationOtp(registration_id: string, code: string): Promise<{ verified: true }> {
  if (registrationLive()) return post('/auth/register/verify', { registration_id, code });
  mockVerify(code);
  return { verified: true };
}

export async function resendRegistrationOtp(registration_id: string): Promise<OtpSentResponse> {
  if (registrationLive()) return post('/auth/register/resend', { registration_id });
  return { otp_sent_to: null, expires_in_s: 600 };
}

export async function submitStudentProfile(req: StudentProfileRequest): Promise<StudentProfileResponse> {
  if (registrationLive()) return post('/auth/register/profile', req);
  return { student_id: mockId('STU'), student_code: null, account_status: 'consent_pending' };
}

export async function submitGuardian(req: GuardianRequest): Promise<GuardianResponse> {
  if (registrationLive()) return post('/consent/guardian', req);
  return { guardian_id: mockId('GRD'), otp_sent_to: mask(req.email), expires_in_s: 600 };
}

export async function verifyGuardianOtp(guardian_id: string, code: string): Promise<{ guardian_verified: true }> {
  if (registrationLive()) return post('/consent/guardian/verify', { guardian_id, code });
  mockVerify(code);
  return { guardian_verified: true };
}

export async function resendGuardianOtp(guardian_id: string): Promise<OtpSentResponse> {
  if (registrationLive()) return post('/consent/guardian/resend', { guardian_id });
  return { otp_sent_to: null, expires_in_s: 600 };
}

/** Null on the mock path: there is no token to issue, and the pages activate locally. */
export async function acceptConsents(req: AcceptConsentRequest): Promise<AcceptConsentResponse | null> {
  if (registrationLive()) return post('/consent/accept', req);
  return null;
}
