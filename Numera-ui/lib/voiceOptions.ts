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
 */
export const TIER_PROVIDER: Record<string, VoiceProvider['id']> = {
  basic: 'inworld',
  premium: 'cartesia',
  enterprise: 'cartesia',
};

/** The providers to offer this student. Empty = backend default only. */
export function providersForTier(tier: string | null | undefined): VoiceProvider[] {
  const id = tier ? TIER_PROVIDER[tier.toLowerCase()] : undefined;
  if (!id) return [];
  return VOICE_PROVIDERS.filter((p) => p.id === id);
}
