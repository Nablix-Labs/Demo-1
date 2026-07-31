/**
 * Tutor voice variants — testing-only catalogue.
 *
 * Manjusha asked for a way to try different tutor voices (2026-07-26). The
 * provider keys below are the adapters actually registered on the voice server
 * (`register_tts_adapter(...)` in app/services/voice/), so they are the only
 * values `VOICE_TTS_PROVIDER` can legally take.
 *
 * ── Backend support (live since PR #39) ─────────────────────────────────────
 * A selection made here is now honoured end to end: `VoiceTTSRequest` carries
 * `provider`/`voice` (app/api/voice.py), and the streaming server reads the
 * `tts_provider`/`tts_voice` query params (streaming_server.py:310), each
 * falling back to the `VOICE_TTS_PROVIDER` / `VOICE_TTS_VOICE` env defaults.
 *
 * ── Why these voice IDs ─────────────────────────────────────────────────────
 * Every id below is copied from the adapter that resolves it, so nothing here
 * can drift into a value the provider rejects: Cartesia UUIDs from
 * CARTESIA_VOICES, Inworld names from INWORLD_VOICES, plus OpenAI's published
 * set. Providers whose catalogue isn't in the repo still take a free-text id
 * pasted from their own playground.
 */

export interface VoiceProvider {
  /** Adapter key registered on the voice server — what VOICE_TTS_PROVIDER takes. */
  id: 'openai' | 'cartesia' | 'inworld' | 'deepgram' | 'mock';
  label: string;
  /** Verifiable voice IDs. The first is the adapter's own default. */
  voices: { id: string; label: string }[];
  /** Where a tester can find more IDs to paste in. */
  browseAt?: string;
}

export const VOICE_PROVIDERS: VoiceProvider[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    voices: [
      { id: 'nova', label: 'Nova (default)' },
      { id: 'alloy', label: 'Alloy' },
      { id: 'echo', label: 'Echo' },
      { id: 'fable', label: 'Fable' },
      { id: 'onyx', label: 'Onyx' },
      { id: 'shimmer', label: 'Shimmer' },
    ],
  },
  {
    // UUIDs mirror CARTESIA_VOICES in cartesia_tts_adapter.py. The first was
    // previously labelled "Barbershop Man" here — it is Skylar (Aditya, 2026-07-27).
    id: 'cartesia',
    label: 'Cartesia',
    voices: [
      { id: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4', label: 'Skylar — Friendly Guide (default)' },
      { id: '573e3144-a684-4e72-ac2b-9b2063a50b53', label: 'Teacher Lady' },
      { id: 'bd9120b6-7761-47a6-a446-77ca49132781', label: 'Tutorial Man' },
      { id: 'e00d0e4c-a5c8-443f-a8a3-473eb9a62355', label: 'Friendly Sidekick' },
      { id: '156fb8d2-335b-4950-9cb3-a2d33befec77', label: 'Helpful Woman' },
      { id: '00a77add-48d5-4ef6-8157-71e5437b282d', label: 'Calm Lady' },
      { id: 'e3827ec5-697a-4b7c-9704-1a23041bbc51', label: 'Sweet Lady' },
      { id: '15a9cd88-84b0-4a8b-95f2-5d583b54c72e', label: 'Reading Lady' },
    ],
    browseAt: 'play.cartesia.ai',
  },
  {
    // Names mirror INWORLD_VOICES in inworld_tts_adapter.py — Inworld takes the
    // name string itself as the voice id, not a UUID.
    id: 'inworld',
    label: 'Inworld',
    voices: [
      { id: 'Ashley', label: 'Ashley — warm, natural female (default)' },
      { id: 'Dennis', label: 'Dennis — smooth, calm, friendly male' },
      { id: 'Olivia', label: 'Olivia — upbeat, friendly British female' },
      { id: 'Alex', label: 'Alex — energetic, expressive male' },
      { id: 'Julia', label: 'Julia — clear female' },
      { id: 'Sarah', label: 'Sarah — friendly female' },
      { id: 'Claire', label: 'Claire — approachable female' },
      { id: 'Priya', label: 'Priya — warm female' },
    ],
    browseAt: 'platform.inworld.ai/tts-playground',
  },
  {
    id: 'deepgram',
    label: 'Deepgram',
    voices: [{ id: 'aura-2-thalia-en', label: 'Aura 2 Thalia (default)' }],
    browseAt: 'developers.deepgram.com',
  },
  { id: 'mock', label: 'Mock (no audio)', voices: [{ id: 'mock', label: 'Mock' }] },
];

export const providerById = (id: string): VoiceProvider | undefined =>
  VOICE_PROVIDERS.find((p) => p.id === id);

/** A short line for the "Test voice" button — enough words to judge a voice by. */
export const VOICE_SAMPLE_TEXT =
  "Let's solve this together. What do you think we should do first?";

/**
 * Which TTS provider a student's subscription gets.
 *
 * The picker used to list every provider to everyone, which is wrong twice: a
 * basic-tier student could pick Cartesia at ~7.5x the cost per character, and
 * the list implies a choice the product doesn't actually offer (Manjusha,
 * 2026-07-28).
 *
 * Tier values are the real ones in `identity.user_credentials.tier`
 * (basic / premium / enterprise), not the free/premium pair in the original
 * TTS design note. The split follows that note's reasoning: Inworld is ~$5 per
 * million characters and sustainable at volume, Cartesia is ~$38 but has much
 * lower time-to-first-audio.
 *
 * NOTE FOR PRODUCT: OpenAI is deliberately unassigned — say which tier should
 * get it (if any) and this is a one-line change. An unknown or missing tier
 * falls back to the backend default, which is the safe direction: it never
 * silently upgrades someone onto the expensive provider.
 *
 * ── 31 Jul: Inworld for every tier (Manjusha) ───────────────────────────────
 * "Let's keep inworld models instead of Cartesia." Cartesia has run out of
 * credits twice in four days (~$38/M chars vs Inworld's ~$5/M), so Inworld is
 * now the product voice across all tiers. The server env default agrees
 * (VOICE_TTS_PROVIDER=inworld on the VM). Cartesia stays registered as the
 * degradation target in lib/tts.ts — if Inworld hard-fails, a topped-up
 * Cartesia account is the backup voice, and switching back is this map again.
 */
export const TIER_PROVIDER: Record<string, VoiceProvider['id']> = {
  basic: 'inworld',
  premium: 'inworld',
  enterprise: 'inworld',
};

/** The providers to offer this student. Empty = backend default only. */
export function providersForTier(tier: string | null | undefined): VoiceProvider[] {
  const id = tier ? TIER_PROVIDER[tier.toLowerCase()] : undefined;
  if (!id) return [];
  return VOICE_PROVIDERS.filter((p) => p.id === id);
}

/**
 * The provider/voice to send when the student hasn't picked one.
 *
 * The backend's own default is broken: POST /voice/tts with no provider returns
 * 502 "Text-to-speech is unavailable right now", while the same call WITH an
 * explicit provider returns audio (verified 2026-07-28). Sending nothing
 * therefore meant every reply fell back to the browser's robotic voice.
 *
 * Naming the tier's provider explicitly sidesteps that entirely, and is what we
 * want anyway — the student hears the voice their plan includes rather than
 * whatever the server env happens to be set to.
 */
export function defaultVoiceForTier(
  tier: string | null | undefined,
): { provider: string; voice: string } | null {
  const provider = providersForTier(tier)[0];
  if (!provider || !provider.voices.length) return null;
  return { provider: provider.id, voice: provider.voices[0].id };
}

/**
 * A provider to try when the student's own one fails.
 *
 * Providers die for reasons the frontend can't see or fix — on 2026-07-28 the
 * Inworld account ran out of credits and every basic-tier reply came back 502
 * ("You have no credits remaining"), dropping students onto the browser's
 * robotic voice. Trying another real provider before giving up keeps the tutor
 * sounding like the tutor.
 *
 * Returns null once every provider has been tried.
 */
export function alternateProvider(
  tried: string | null | undefined,
  skip: ReadonlySet<string> = new Set(),
): { provider: string; voice: string } | null {
  const next = VOICE_PROVIDERS.find(
    (p) => p.id !== tried && p.id !== 'mock' && !skip.has(p.id) && p.voices.length > 0,
  );
  return next ? { provider: next.id, voice: next.voices[0].id } : null;
}
