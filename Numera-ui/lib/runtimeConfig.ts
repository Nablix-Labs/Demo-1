/**
 * Numera — runtime configuration from NEXT_PUBLIC_* env vars.
 *
 * Every env read here MUST be a static `process.env.NEXT_PUBLIC_X` access:
 * Next.js inlines these at build time by literal text replacement, so
 * dynamic lookups (process.env[name]) come back undefined in the browser.
 */

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, "");

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

export const buildVoiceStreamUrl = (sessionId: string): string => {
  if (!voiceStreamingEnabled || !voiceWsUrl) {
    throw new Error(
      "Voice streaming is disabled or NEXT_PUBLIC_VOICE_WS_URL/NEXT_PUBLIC_WS_URL is missing",
    );
  }

  const params = new URLSearchParams({
    session_id: sessionId,
    student_id: "ST001",
  });
  return `${voiceWsUrl}?${params.toString()}`;
};
