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
  /**
   * The student's workbook code (`ST###`) — what every tutoring call must send
   * as `student_id`.
   *
   * NOT SENT YET. Verified against the auth service on 2026-07-28: `login()`
   * returns only access_token/token_type/role/tier/last_journey_state, the JWT
   * payload is `{sub, role, tier, iat, exp}` where `sub` is the integer user_id,
   * and `last_journey_state` has the code projected out of it. So there is no
   * way to derive this client-side — it needs the backend to include it
   * (`auth_service.login` already loads the student row for the journey lookup).
   *
   * Until then the tutoring calls fall back to the fixed ST001, which is why a
   * logged-in student who isn't ST001's owner gets 403 STUDENT_FORBIDDEN from
   * student_model (issue #40). Reading it here means the fix lands with the
   * backend field and needs no further frontend change.
   */
  student_code?: string | null;
  /**
   * Where this student left off, projected from student_model by the auth
   * service. Null for a student who has never started a topic — which is the
   * signal to send them to the diagnostic. `current_phase` uses the Student
   * Model's own names (PHASE_0_DIAGNOSTIC, …); see landingRoute().
   */
  last_journey_state?: {
    topic_id?: string | null;
    current_phase?: string | null;
    recommended_entry_phase?: string | null;
  } | null;
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

/** Error body the auth server returns on every non-2xx (verified 2026-07-28). */
interface AuthErrorBody {
  error_code?: string;
  message?: string;
  field?: string | null;
}

/**
 * Student-facing copy for a failed login, chosen by the server's `error_code`
 * and falling back to the HTTP status.
 *
 * The status alone is not enough. Probed against https://nablix.ai:8080 on
 * 2026-07-28, /auth/login only ever answers:
 *   401 INVALID_CREDENTIALS — wrong password OR unknown email (it deliberately
 *                             does not distinguish the two)
 *   422 VALIDATION_ERROR    — the email itself is malformed
 * It never returns 404. So a 404 here did NOT come from the auth API — it came
 * from whatever is in front of it (the nginx `/nablix-auth` location missing on
 * the VM returns a plain nginx 404 page). Reporting that as "no account found"
 * told Manjusha her account didn't exist when the account was fine and the
 * proxy was the problem (2026-07-27). Treat it as unreachable, not as a
 * rejected sign-in.
 */
function messageForError(status: number, body: AuthErrorBody | null): string {
  switch (body?.error_code) {
    case 'INVALID_CREDENTIALS':
      return "That email and password don't match. Please try again.";
    case 'VALIDATION_ERROR':
      return body.field === 'email'
        ? 'Please enter a valid email address.'
        : 'Please check your details and try again.';
  }
  switch (status) {
    case 400: return 'Please enter a valid email and password.';
    case 401: return "That email and password don't match. Please try again.";
    // Not the auth API — see above. 5xx gateway codes mean the same thing.
    case 404:
    case 502:
    case 503:
    case 504: return "Can't reach the sign-in service right now. Please try again shortly.";
    case 500: return 'The server ran into a problem. Please try again in a moment.';
    default:  return 'Could not log you in. Please try again.';
  }
}

/** Parse the JSON error body, tolerating the HTML error pages a proxy returns. */
async function readErrorBody(res: Response): Promise<AuthErrorBody | null> {
  try {
    const body = (await res.json()) as unknown;
    return body && typeof body === 'object' ? (body as AuthErrorBody) : null;
  } catch {
    return null;
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
  if (!res.ok) {
    const body = await readErrorBody(res);
    // The server's own message is developer-facing, so it never reaches the
    // student — but it's the only clue when the proxy is misconfigured.
    console.error('[auth] login failed', { status: res.status, url: `${AUTH_BASE}/auth/login`, body });
    throw new LoginError(res.status, messageForError(res.status, body));
  }
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

/** setTimeout stores its delay in a signed 32-bit int; anything longer fires
 *  immediately. ~24.8 days, so a re-arm rather than a single long sleep. */
const MAX_TIMEOUT_MS = 2_147_483_647;

/**
 * Milliseconds until `token` stops being valid, for scheduling a re-check.
 *
 * Null when there is nothing to wait for: no token, or no `exp` claim to
 * expire. 0 when it has already lapsed.
 *
 * Expiry is the one access change no user action announces — the token simply
 * goes stale while the student sits on a page. Without a timer the app finds
 * out at the next navigation, which for a student left on the lesson screen is
 * never: "it never logs me out, even after hours" (Manjusha, 11 Aug).
 */
export function msUntilExpiry(token: string | null | undefined): number | null {
  if (!token) return null;
  const claims = decodeJwt(token);
  if (!claims?.exp) return null;
  // Matches isTokenValid's skew margin, so the re-check lands after the token
  // is already considered invalid rather than a beat before.
  const remaining = claims.exp * 1000 - 5_000 - Date.now();
  return Math.min(Math.max(remaining, 0), MAX_TIMEOUT_MS);
}
