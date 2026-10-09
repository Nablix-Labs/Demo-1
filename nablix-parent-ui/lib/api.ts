/**
 * Where the portal's data comes from.
 *
 * NEXT_PUBLIC_PARENT_API_MODE:
 *  - "sample" (default): lib/sample.ts. No backend serves parents yet.
 *  - "http": the parent endpoints proposed in docs/BACKEND-ASKS.md, behind a
 *    parent_guardian login. Switch to it once they exist; nothing else changes.
 */
import type { Child, ChildData, ConsentPurpose, ConsentRecord } from './types';
import { sampleChildData, SAMPLE_CHILDREN } from './sample';

export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
export const MODE = (process.env.NEXT_PUBLIC_PARENT_API_MODE ?? 'sample') as 'sample' | 'http';
export const isSample = MODE === 'sample';

const API = process.env.NEXT_PUBLIC_PARENT_API_BASE ?? '/api';
const AUTH = process.env.NEXT_PUBLIC_AUTH_API_BASE ?? '/nablix-auth';

const TOKEN_KEY = 'nablix.parent.token';
const EMAIL_KEY = 'nablix.parent.email';

function store(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export const getToken = () => store()?.getItem(TOKEN_KEY) ?? null;
export const signedInEmail = () => store()?.getItem(EMAIL_KEY) ?? null;

export function signOut() {
  store()?.removeItem(TOKEN_KEY);
  store()?.removeItem(EMAIL_KEY);
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/** POST /auth/login — only a parent/guardian account may continue. */
export async function signIn(email: string, password: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${AUTH}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password }),
    });
  } catch {
    throw new ApiError('Could not reach Numera. Check your connection and try again.', 0);
  }
  const body = (await res.json().catch(() => ({}))) as { access_token?: string; role?: string; message?: string };
  if (res.status === 401) throw new ApiError('Wrong email or password.', 401);
  if (!res.ok || !body.access_token) throw new ApiError(body.message || `Sign-in failed (${res.status}).`, res.status);
  if (body.role !== 'parent_guardian') {
    throw new ApiError('This is not a parent account. Sign in with the email you gave when your child signed up.', 403);
  }
  store()?.setItem(TOKEN_KEY, body.access_token);
  store()?.setItem(EMAIL_KEY, email.trim());
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { Accept: 'application/json', Authorization: `Bearer ${getToken() ?? ''}` },
  });
  if (res.status === 401) {
    signOut();
    throw new ApiError('Your sign-in has expired. Please sign in again.', 401);
  }
  if (!res.ok) throw new ApiError(`Could not load your child's progress (${res.status}).`, res.status);
  return res.json() as Promise<T>;
}

async function send<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken() ?? ''}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(`That change was not saved (${res.status}).`, res.status);
  return res.json() as Promise<T>;
}

// In sample mode each child is generated once per tab, so consent changes stick.
const sampleCache = new Map<string, ChildData>();
const sample = (code: string) => {
  if (!sampleCache.has(code)) sampleCache.set(code, sampleChildData(new Date(), code));
  return sampleCache.get(code)!;
};

export async function listChildren(): Promise<Child[]> {
  if (isSample) return SAMPLE_CHILDREN;
  return get<Child[]>('/parent/children');
}

export async function loadChild(code: string): Promise<ChildData> {
  if (isSample) return sample(code);
  const c = encodeURIComponent(code);
  const [children, topics, sessions, misconceptions, consents] = await Promise.all([
    listChildren(),
    get<ChildData['topics']>(`/parent/children/${c}/topics`),
    get<ChildData['sessions']>(`/parent/children/${c}/sessions?days=90`),
    get<ChildData['misconceptions']>(`/parent/children/${c}/misconceptions`),
    get<ChildData['consents']>(`/parent/children/${c}/consents`),
  ]);
  const child = children.find((x) => x.student_code === code);
  if (!child) throw new ApiError('That child is not linked to your account.', 404);
  return { child, topics, sessions, misconceptions, consents };
}

/** Grant or withdraw one optional consent. Mandatory ones withdraw the account. */
export async function setConsent(code: string, purpose: ConsentPurpose, granted: boolean): Promise<ConsentRecord> {
  if (isSample) {
    const rec = sample(code).consents.find((x) => x.purpose === purpose)!;
    const now = new Date().toISOString();
    Object.assign(rec, granted ? { accepted_at: now, withdrawn_at: null } : { withdrawn_at: now });
    return { ...rec };
  }
  return send<ConsentRecord>(`/parent/children/${encodeURIComponent(code)}/consents`, { purpose, granted });
}
