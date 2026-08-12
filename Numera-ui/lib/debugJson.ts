/**
 * Developer-only capture of the JSON behind the last interaction.
 *
 * Manjusha, 12 Aug 2026: "I need a proper way to display the json (dev only) so
 * we can easily check, debug and test everything" — without logging into the
 * Azure VM or reading server logs. The spec's contract is Chiru's `debug` object
 * carrying `student_model_request` and `student_model_response`.
 *
 * Two deliberate decisions:
 *
 *   1. Capture happens once, in the API layer, not per screen. Every phase is
 *      covered the moment it makes a call, and removing the feature is deleting
 *      files rather than hunting call sites — Manjusha asked for it to be easy
 *      to add and delete, because it is temporary.
 *
 *   2. The tutor request/response are captured too, not just the Student Model
 *      pair. Chiru's side has not shipped yet, so a panel that reads only
 *      `debug` would show nothing at all today; this way testers get the payload
 *      they are already screenshotting by hand, and the Student Model tabs light
 *      up on their own when his field arrives.
 *
 * This is a view onto what was already exchanged. It never re-requests anything
 * and never modifies a payload (spec §4.2, "the view is read-only").
 */

/** The debug object the backend attaches when debug mode is on (spec §3.3). */
export interface BackendDebugObject {
  student_model_request?: unknown;
  student_model_response?: unknown;
}

export interface DebugCapture {
  /** Which call this came from, e.g. "POST /interaction". */
  endpoint: string;
  /** Local clock, for telling two captures apart in a screenshot. */
  at: string;
  /** What the frontend sent. */
  request: unknown;
  /** What the backend sent back. */
  response: unknown;
  /** Chiru's capture of the real Student Model exchange, when present. */
  studentModelRequest: unknown;
  studentModelResponse: unknown;
}

/**
 * Whether the debug view is available at all.
 *
 * Off unless explicitly switched on at build time, so a production bundle has no
 * debug control (spec §3.4: "must not be exposed to normal students"). The
 * panel additionally hides itself when nothing has been captured.
 */
export function debugJsonEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DEBUG_JSON === 'true';
}

/** Pull the backend's debug object off a response, if it sent one. */
export function backendDebugObject(response: unknown): BackendDebugObject | null {
  if (typeof response !== 'object' || response === null) return null;
  const debug = (response as { debug?: unknown }).debug;
  if (typeof debug !== 'object' || debug === null) return null;
  return debug as BackendDebugObject;
}

/**
 * Keys whose values must never be rendered (spec §3.4).
 *
 * The debug object is not supposed to contain credentials, but this view is
 * shown on screen and screenshotted into a group chat, so it does not rely on
 * the backend having got that right.
 */
const REDACTED_KEYS = [
  'authorization', 'access_token', 'refresh_token', 'id_token', 'token',
  'password', 'secret', 'api_key', 'apikey', 'client_secret', 'bearer',
  'cookie', 'set-cookie', 'connection_string',
];

function isRedacted(key: string): boolean {
  const lower = key.toLowerCase();
  return REDACTED_KEYS.some((needle) => lower === needle || lower.endsWith(`_${needle}`));
}

/**
 * Deep copy with secrets replaced, and cycles broken.
 *
 * A cycle would make JSON.stringify throw inside the panel's render, taking the
 * screen down with it — a debug tool must never be the thing that breaks the
 * session it is there to observe.
 */
export function redactForDisplay(value: unknown, seen: WeakSet<object> = new WeakSet()): unknown {
  if (typeof value !== 'object' || value === null) return value;
  if (seen.has(value)) return '[circular]';
  seen.add(value);
  if (Array.isArray(value)) return value.map((entry) => redactForDisplay(entry, seen));
  const out: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
    out[key] = isRedacted(key) ? '[redacted]' : redactForDisplay(entry, seen);
  }
  return out;
}

/** Pretty-print for the panel. Never throws — see redactForDisplay. */
export function formatJson(value: unknown): string {
  if (value === undefined) return 'Not provided by the backend.';
  try {
    return JSON.stringify(redactForDisplay(value), null, 2);
  } catch {
    return 'Could not render this payload.';
  }
}

/** Build a capture from one completed call. */
export function toDebugCapture(
  endpoint: string,
  request: unknown,
  response: unknown,
  at: string,
): DebugCapture {
  const debug = backendDebugObject(response);
  return {
    endpoint,
    at,
    request,
    response,
    studentModelRequest: debug?.student_model_request,
    studentModelResponse: debug?.student_model_response,
  };
}

// ── The capture itself ────────────────────────────────────────────────────────
//
// A module-level store rather than a slice of useNumeraStore, so that removing
// this feature is deleting two files and two lines — nothing left behind in the
// app's real state, and nothing persisted. It holds only the most recent call:
// testers want "what did that click just send", not a session history, and the
// spec puts a monitoring dashboard explicitly out of scope (§6).

let capture: DebugCapture | null = null;
const listeners = new Set<() => void>();

/** Record one completed call. No-op unless the debug view is switched on. */
/**
 * Calls worth capturing — the ones that carry a Student Model exchange.
 *
 * Manjusha, 12 Aug 2026: "it comes and disappears as tts endpoint is called
 * after that — always I see tts json only". Capturing every call meant the
 * tutor turn she needed was overwritten a moment later by `/voice/tts`, which
 * fires on every spoken reply and has no Student Model exchange behind it.
 *
 * An allow-list rather than a block-list: a new noisy endpoint should be
 * ignored by default, not silently start clobbering the turn under inspection.
 */
const CAPTURED_ENDPOINTS = [
  '/interaction',
  '/canvas/submit',
  '/session/start',
  '/session/end',
  '/diagnostic/complete',
  '/orientation/start',
  '/orientation/complete',
  '/review/complete',
];

/** Is this a call a tester wants to inspect, or transport noise? */
export function isCapturedEndpoint(endpoint: string): boolean {
  // The label is "<METHOD> <path>", optionally with a " (failed)" suffix.
  const path = endpoint.replace(/^\S+\s+/, '').replace(/\s*\(failed\)\s*$/, '');
  // Voice transport is never interesting here, and must be rejected FIRST:
  // "/voice/session/start" ends with "/session/start" and would otherwise be
  // captured by the allow-list below.
  if (path.startsWith('/voice/')) return false;
  return CAPTURED_ENDPOINTS.some((allowed) => path === allowed || path.endsWith(allowed));
}

export function recordDebugCall(
  endpoint: string,
  request: unknown,
  response: unknown,
): void {
  if (!debugJsonEnabled()) return;
  if (!isCapturedEndpoint(endpoint)) return;
  capture = toDebugCapture(endpoint, request, response, new Date().toLocaleTimeString());
  for (const listener of listeners) listener();
}

export function subscribeDebugCapture(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getDebugCapture(): DebugCapture | null {
  return capture;
}

/** Server render has no capture; keeps useSyncExternalStore hydration-safe. */
export function getDebugCaptureServer(): DebugCapture | null {
  return null;
}

/** Drop what was captured — used when a session ends. */
export function clearDebugCapture(): void {
  capture = null;
  for (const listener of listeners) listener();
}
