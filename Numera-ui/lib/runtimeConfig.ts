/**
 * Numera — runtime configuration from NEXT_PUBLIC_* env vars.
 *
 * Every env read here MUST be a static `process.env.NEXT_PUBLIC_X` access:
 * Next.js inlines these at build time by literal text replacement, so
 * dynamic lookups (process.env[name]) come back undefined in the browser.
 */

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, "");

/**
 * Base path the app is served under (e.g. "/app" on the VM), set by next.config
 * from EXPORT_BASE_PATH. Raw /public asset URLs are NOT auto-prefixed the way
 * next/link hrefs are, so loaders (the 3D model) must prepend this.
 */
export const basePath: string = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/**
 * Voice streaming WebSocket URL. Accepts the new NEXT_PUBLIC_VOICE_WS_URL
 * name, falling back to the legacy NEXT_PUBLIC_WS_URL still used by
 * .env.local and the build:selfhost script.
 */
const rawVoiceWsUrl =
  process.env.NEXT_PUBLIC_VOICE_WS_URL ?? process.env.NEXT_PUBLIC_WS_URL;

export const voiceWsUrl: string | null = rawVoiceWsUrl
  ? trimTrailingSlash(rawVoiceWsUrl)
  : null;

/**
 * Voice streaming is on when a WS URL is configured, unless explicitly
 * disabled. Opt-out (rather than opt-in) keeps existing deployments that
 * only set the URL working without a new required flag.
 */
export const voiceStreamingEnabled: boolean =
  voiceWsUrl !== null &&
  process.env.NEXT_PUBLIC_ENABLE_VOICE_STREAMING !== "false";

/**
 * Testing escape hatch: the tutoring backend requires a bearer token on
 * /interaction, /hint, /canvas and /voice, but the sign-up flow doesn't log in
 * to the auth server yet, so a student who signs up has no token and every one
 * of those calls 401s. With this flag on, anonymous students send a placeholder
 * bearer so testing isn't blocked. Off by default — a real token, once we have
 * one, always takes precedence over the placeholder.
 */
export const allowAnonTutorCalls: boolean =
  process.env.NEXT_PUBLIC_ALLOW_ANON_TUTOR === "true";

export const buildVoiceStreamUrl = (sessionId: string): string => {
  if (!voiceStreamingEnabled || !voiceWsUrl) {
    throw new Error(
      "Voice streaming is disabled or NEXT_PUBLIC_VOICE_WS_URL/NEXT_PUBLIC_WS_URL is missing",
    );
  }

  // The streaming voice server reads `session` (not `session_id`); a mismatch
  // makes it fall back to "default", which fails its ^SESSION\d{3}$ check.
  const params = new URLSearchParams({
    session: sessionId,
    student_id: "ST001",
  });
  return `${voiceWsUrl}?${params.toString()}`;
};
