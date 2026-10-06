/**
 * Approver sign-in (authoring API reference, "Quick start" §1–2).
 *
 * Every /authoring/* route needs `role: admin`. The token from POST
 * /auth/login is kept for the browser tab's session and sent as a bearer on
 * every request; a 401 (INVALID_TOKEN / TOKEN_EXPIRED) drops it and sends the
 * approver back to /login, which is the reference's "re-login and retry".
 *
 * Only used in `http` mode — the mock serves sample data and needs no login.
 */

/** Where the portal is mounted (`/portal` on the VM, empty locally). */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? '';

const TOKEN_KEY = 'nablix.portal.token';
const EMAIL_KEY = 'nablix.portal.email';

/** Fired on window when a page load fails; `detail` is the message. */
export const API_ERROR_EVENT = 'portal:api-error';

export const authRequired = (process.env.NEXT_PUBLIC_API_MODE ?? 'mock') === 'http';

/** Where /auth/login lives. Same origin by default (next.config rewrites it). */
const authBase = process.env.NEXT_PUBLIC_AUTH_API_BASE ?? '';

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return storage()?.getItem(TOKEN_KEY) ?? null;
}

export function signedInEmail(): string | null {
  return storage()?.getItem(EMAIL_KEY) ?? null;
}

export function signOut(): void {
  storage()?.removeItem(TOKEN_KEY);
  storage()?.removeItem(EMAIL_KEY);
}

/** Send the approver to sign in, remembering where they were. */
export function redirectToLogin(): void {
  if (typeof window === 'undefined') return;
  signOut();
  // `next` is a route inside the app, so without the base path — the router
  // adds it back on the way in.
  const path = window.location.pathname.slice(BASE_PATH.length) || '/';
  if (path.startsWith('/login')) return;
  window.location.assign(`${BASE_PATH}/login?next=${encodeURIComponent(path + window.location.search)}`);
}

export class AuthError extends Error {}

/** POST /auth/login. Rejects with a message fit to show on the form. */
export async function signIn(email: string, password: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${authBase}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ email: email.trim(), password }),
    });
  } catch {
    throw new AuthError('Could not reach the authoring server. Check your connection and try again.');
  }
  const body = (await res.json().catch(() => ({}))) as {
    access_token?: string;
    role?: string;
    error_code?: string;
    message?: string;
  };
  if (!res.ok || !body.access_token) {
    if (res.status === 401) throw new AuthError('Wrong email or password.');
    throw new AuthError(body.message || `Sign-in failed (${res.status}).`);
  }
  // The login succeeds for any account, but every authoring route is admin-only
  // and would 403 one by one. Say so once, here.
  if (body.role && body.role !== 'admin') {
    throw new AuthError('This account is not an approver. Sign in with an admin account.');
  }
  storage()?.setItem(TOKEN_KEY, body.access_token);
  storage()?.setItem(EMAIL_KEY, email.trim());
}
