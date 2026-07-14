'use client';

/**
 * Nablix auth API — real login against the Nablix platform.
 *
 *   POST {AUTH_BASE}/auth/login  { email, password }
 *     → { access_token, token_type, role, tier }
 *
 * The returned JWT is a bearer token: attach it as `Authorization: Bearer <token>`
 * on subsequent authenticated requests (see the interceptor in lib/api.ts).
 *
 * The auth service lives on its own host/port, separate from the tutoring API
 * (NEXT_PUBLIC_API_BASE_URL), so it has its own base URL.
 */

// Same-origin by default so the browser isn't blocked by CORS — the platform's
// auth server (https://nablix.ai:8080) doesn't send CORS headers, so we reach it
// through a reverse proxy on this path (Next rewrite in dev; nginx in prod,
// exactly like the tutoring API's /api). Override with NEXT_PUBLIC_AUTH_BASE_URL
// to hit the auth host directly once it allows the browser origin.
const AUTH_BASE = (process.env.NEXT_PUBLIC_AUTH_BASE_URL ?? '/nablix-auth').replace(/\/+$/, '');

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
  tier: string;
}

/** Thrown on any non-2xx (or unreachable) login; `status` is 0 when the request never landed. */
export class LoginError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'LoginError';
    this.status = status;
  }
}

// Student-facing copy per documented status codes (400/401/404/500).
function messageForStatus(status: number): string {
  switch (status) {
    case 400: return 'Please enter a valid email and password.';
    case 401: return "That email and password don't match. Please try again.";
    case 404: return 'No account found for that email.';
    case 500: return 'The server ran into a problem. Please try again in a moment.';
    default:  return 'Could not log you in. Please try again.';
  }
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  let res: Response;
  try {
    res = await fetch(`${AUTH_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
  } catch {
    throw new LoginError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (!res.ok) throw new LoginError(res.status, messageForStatus(res.status));
  return (await res.json()) as LoginResponse;
}

// ── JWT helpers (unverified client-side decode — for reading exp/role only) ──

export interface JwtClaims {
  sub?: string;
  role?: string;
  tier?: string;
  iat?: number;
  exp?: number;
}

function base64UrlDecode(segment: string): string {
  let s = segment.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return atob(s);
}

/** Decode a JWT payload. Never trust this for authorization — the server does
 *  that; it's only for reading non-secret claims (exp, role) in the UI. */
export function decodeJwt(token: string): JwtClaims | null {
  try {
    return JSON.parse(base64UrlDecode(token.split('.')[1])) as JwtClaims;
  } catch {
    return null;
  }
}

/** True when the token exists and its exp is comfortably in the future. */
export function isTokenValid(token: string | null | undefined): boolean {
  if (!token) return false;
  const claims = decodeJwt(token);
  if (!claims?.exp) return false;
  return claims.exp * 1000 > Date.now() + 5_000; // small clock-skew margin
}
