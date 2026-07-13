'use client';

/**
 * Auth / consent / RBAC store — the student account lifecycle.
 *
 * Mirrors the backend proposal (Student Registration, Login, Consent & RBAC)
 * without a backend: identity + consent + account_status are modelled here so
 * the demo can walk the real flow. The mapping is deliberate:
 *   authentication  → confirms WHO the user is   (authMethod / verified)
 *   consent_records → confirms the student is ALLOWED to use the platform
 *   user_roles      → controls WHAT the user can access (role + accessDecision)
 *
 * OTP is treated as short-lived (never stored); we only keep the verified flag.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { isTokenValid } from '@/lib/auth/authApi';

// account_status values from §12 of the proposal.
export type AccountStatus =
  | 'registration_started'
  | 'consent_pending'
  | 'active'
  | 'consent_withdrawn'
  | 'suspended'
  | 'locked'
  | 'deleted';

export type AuthMethod = 'sso' | 'email_otp' | 'phone_otp' | 'password';
export type SsoProvider = 'google' | 'microsoft' | 'apple' | 'school';
export type Role = 'student' | 'parent_guardian';

// consent_records purposes from §7. All mandatory except marketing.
export type ConsentPurpose =
  | 'account_creation'
  | 'ai_tutor_usage'
  | 'canvas_processing'
  | 'voice_processing'
  | 'learning_analytics'
  | 'safety_monitoring'
  | 'marketing';

export const CONSENT_PURPOSES: {
  id: ConsentPurpose;
  label: string;
  detail: string;
  mandatory: boolean;
}[] = [
  { id: 'account_creation', label: 'Account creation', detail: 'Create and manage the student account.', mandatory: true },
  { id: 'ai_tutor_usage', label: 'AI tutor usage', detail: 'Let the student learn with the AI maths tutor.', mandatory: true },
  { id: 'canvas_processing', label: 'Canvas processing', detail: 'Read and give feedback on written working on the canvas.', mandatory: true },
  { id: 'voice_processing', label: 'Voice processing', detail: 'Enable voice input and voice-based tutoring.', mandatory: true },
  { id: 'learning_analytics', label: 'Learning analytics', detail: 'Store progress, session history and feedback.', mandatory: true },
  { id: 'safety_monitoring', label: 'Safety monitoring', detail: 'Apply safeguarding rules to student interactions.', mandatory: true },
  { id: 'marketing', label: 'Marketing updates', detail: 'Optional product news. Off by default.', mandatory: false },
];

export const MANDATORY_PURPOSES = CONSENT_PURPOSES.filter((p) => p.mandatory).map((p) => p.id);

// Purposes whose withdrawal blocks the whole account (§7 "mandatory consent
// withdrawn → restrict access"). voice_processing / canvas_processing are
// feature-level (§10): required to USE that feature, but their withdrawal just
// disables the feature, not the account.
export const ACCOUNT_BLOCKING_PURPOSES: ConsentPurpose[] = [
  'account_creation',
  'ai_tutor_usage',
  'learning_analytics',
  'safety_monitoring',
];

// Feature consents gated per-feature in the UI (§10 / §14 messages).
export const FEATURE_PURPOSES: ConsentPurpose[] = ['voice_processing', 'canvas_processing'];

export const SAFETY_DISCLOSURE_VERSION = 'v1.0';

interface ConsentRecord {
  acceptedAt: string | null;
  withdrawnAt: string | null;
}

interface StudentProfile {
  name: string;
  ageBand: string;   // e.g. "11-14 (KS3)"
  gradeBand: string; // e.g. "Year 9"
  preferredMode: 'voice' | 'text' | 'balanced';
}

interface Guardian {
  name: string;
  relationship: string; // parent / guardian / carer
  email: string;
  phone: string;
  verified: boolean; // OTP/SSO identity confirmed (not consent)
}

interface AuthState {
  accountStatus: AccountStatus;
  role: Role | null;
  authMethod: AuthMethod | null;
  ssoProvider: SsoProvider | null;
  email: string;
  phone: string;
  student: StudentProfile;
  guardian: Guardian;
  consents: Record<ConsentPurpose, ConsentRecord>;
  disclosureAck: { acknowledged: boolean; version: string; at: string | null };

  // Real auth (Nablix platform) — JWT + tier from POST /auth/login. A valid
  // token means the server already authenticated the user, so it grants access
  // directly (see accessDecision). Registration/consent are still modelled
  // client-side until those endpoints exist.
  accessToken: string | null;
  tier: string | null;

  // Registration
  startRegistration: (method: AuthMethod, opts?: { email?: string; phone?: string; ssoProvider?: SsoProvider }) => void;
  setStudentProfile: (p: Partial<StudentProfile>) => void;
  setGuardian: (g: Partial<Guardian>) => void;
  verifyGuardian: () => void; // mock OTP/SSO success

  // Consent
  acceptConsents: (accepted: ConsentPurpose[]) => void;
  acknowledgeDisclosure: () => void;
  withdrawConsent: (purpose: ConsentPurpose) => void;
  grantConsent: (purpose: ConsentPurpose) => void; // (re-)grant a single consent

  // Lifecycle
  loginSuccess: (p: { token: string; role: Role; tier: string; email: string }) => void;
  activateAccount: () => void;
  suspend: () => void;
  logout: () => void;
  reset: () => void;
}

const emptyConsents = (): Record<ConsentPurpose, ConsentRecord> =>
  CONSENT_PURPOSES.reduce((acc, p) => {
    acc[p.id] = { acceptedAt: null, withdrawnAt: null };
    return acc;
  }, {} as Record<ConsentPurpose, ConsentRecord>);

const initial = {
  accountStatus: 'registration_started' as AccountStatus,
  role: null as Role | null,
  authMethod: null as AuthMethod | null,
  ssoProvider: null as SsoProvider | null,
  email: '',
  phone: '',
  student: { name: '', ageBand: '', gradeBand: '', preferredMode: 'balanced' as const },
  guardian: { name: '', relationship: 'Parent', email: '', phone: '', verified: false },
  consents: emptyConsents(),
  disclosureAck: { acknowledged: false, version: SAFETY_DISCLOSURE_VERSION, at: null },
  accessToken: null as string | null,
  tier: null as string | null,
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      ...initial,

      startRegistration: (method, opts = {}) =>
        set({
          authMethod: method,
          ssoProvider: opts.ssoProvider ?? null,
          email: opts.email ?? '',
          phone: opts.phone ?? '',
          role: 'student',
          accountStatus: 'consent_pending',
        }),

      setStudentProfile: (p) => set((s) => ({ student: { ...s.student, ...p } })),
      setGuardian: (g) => set((s) => ({ guardian: { ...s.guardian, ...g } })),
      verifyGuardian: () => set((s) => ({ guardian: { ...s.guardian, verified: true } })),

      acceptConsents: (accepted) =>
        set((s) => {
          const now = new Date().toISOString();
          const consents = { ...s.consents };
          for (const p of CONSENT_PURPOSES) {
            consents[p.id] = accepted.includes(p.id)
              ? { acceptedAt: now, withdrawnAt: null }
              : { acceptedAt: null, withdrawnAt: null };
          }
          return { consents };
        }),

      acknowledgeDisclosure: () =>
        set({ disclosureAck: { acknowledged: true, version: SAFETY_DISCLOSURE_VERSION, at: new Date().toISOString() } }),

      withdrawConsent: (purpose) =>
        set((s) => {
          const consents = { ...s.consents, [purpose]: { acceptedAt: s.consents[purpose].acceptedAt, withdrawnAt: new Date().toISOString() } };
          // Only an account-blocking consent locks the whole account; voice/canvas
          // withdrawal keeps the account active and just gates that feature.
          const accountBroken = ACCOUNT_BLOCKING_PURPOSES.some((p) => !consents[p].acceptedAt || consents[p].withdrawnAt);
          return { consents, accountStatus: accountBroken ? 'consent_withdrawn' : s.accountStatus };
        }),

      grantConsent: (purpose) =>
        set((s) => {
          const consents = { ...s.consents, [purpose]: { acceptedAt: new Date().toISOString(), withdrawnAt: null } };
          // If re-granting restored all account-blocking consents, un-restrict.
          const accountOk = ACCOUNT_BLOCKING_PURPOSES.every((p) => consents[p].acceptedAt && !consents[p].withdrawnAt);
          const accountStatus =
            s.accountStatus === 'consent_withdrawn' && accountOk ? 'active' : s.accountStatus;
          return { consents, accountStatus };
        }),

      // Successful real login: store the JWT + tier and mark the account active
      // for the returned role. The server owns identity/consent, so a valid
      // token is sufficient for access (accessDecision short-circuits on it).
      //
      // The platform authenticated a provisioned, active student — consent was
      // captured during real registration. Until the backend exposes that
      // consent state, mark the mandatory consents satisfied so the feature
      // gates (voice/canvas §10) don't block a legitimately logged-in user.
      // TODO(auth): replace with real consent state once /consent endpoints exist.
      loginSuccess: ({ token, role, tier, email }) =>
        set((s) => {
          const now = new Date().toISOString();
          const consents = { ...s.consents };
          for (const p of MANDATORY_PURPOSES) consents[p] = { acceptedAt: now, withdrawnAt: null };
          return {
            accessToken: token,
            tier,
            role,
            email,
            authMethod: 'password',
            accountStatus: 'active',
            consents,
            disclosureAck: { acknowledged: true, version: SAFETY_DISCLOSURE_VERSION, at: now },
          };
        }),

      activateAccount: () => set({ accountStatus: 'active' }),
      suspend: () => set({ accountStatus: 'suspended' }),
      logout: () => set({ authMethod: null, ssoProvider: null, accessToken: null, tier: null }),
      reset: () => set({ ...initial, consents: emptyConsents() }),
    }),
    {
      name: 'numera-auth',
      storage: createJSONStorage(() => localStorage),
      skipHydration: true,
    },
  ),
);

// ─── RBAC / access decision (§13) ──────────────────────────────────────────────

/** True when every mandatory consent is accepted and not withdrawn (onboarding gate). */
export function hasMandatoryConsents(consents: Record<ConsentPurpose, ConsentRecord>): boolean {
  return MANDATORY_PURPOSES.every((p) => consents[p].acceptedAt && !consents[p].withdrawnAt);
}

/** True when every account-blocking consent is active (drives account access). */
export function hasAccountConsents(consents: Record<ConsentPurpose, ConsentRecord>): boolean {
  return ACCOUNT_BLOCKING_PURPOSES.every((p) => consents[p].acceptedAt && !consents[p].withdrawnAt);
}

/** Is a single consent purpose currently active? */
export function isConsentActive(consents: Record<ConsentPurpose, ConsentRecord>, purpose: ConsentPurpose): boolean {
  const r = consents[purpose];
  return Boolean(r.acceptedAt && !r.withdrawnAt);
}

export type AccessOutcome =
  | { allowed: true }
  | { allowed: false; reason: AccountStatus | 'consent_pending' | 'not_student'; redirect: string };

/**
 * The backend access-decision chain from §13, run client-side for the demo.
 * Returns where to send the user when access is not allowed.
 */
export function accessDecision(
  s: Pick<AuthState, 'accountStatus' | 'role' | 'consents' | 'disclosureAck' | 'accessToken'>,
): AccessOutcome {
  // A valid server-issued token means the platform already authenticated and
  // authorized this user — that decision wins over the client-side mock chain.
  if (isTokenValid(s.accessToken)) return { allowed: true };
  if (s.role !== 'student') return { allowed: false, reason: 'not_student', redirect: '/login' };
  if (s.accountStatus === 'suspended' || s.accountStatus === 'locked' || s.accountStatus === 'deleted')
    return { allowed: false, reason: s.accountStatus, redirect: '/restricted' };
  if (s.accountStatus === 'consent_withdrawn') return { allowed: false, reason: 'consent_withdrawn', redirect: '/restricted' };
  if (s.accountStatus !== 'active' || !hasAccountConsents(s.consents))
    return { allowed: false, reason: 'consent_pending', redirect: '/restricted' };
  return { allowed: true };
}
