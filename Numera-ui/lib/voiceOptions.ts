/**
 * Tutor voice variants — testing-only catalogue.
 *
 * Manjusha asked for a way to try different tutor voices (2026-07-26). The
 * provider keys below are the adapters actually registered on the voice server
 * (`register_tts_adapter(...)` in app/services/voice/), so they are the only
 * values `VOICE_TTS_PROVIDER` can legally take.
 *
 * ── Pending backend support ──────────────────────────────────────────────────
 * The backend does NOT accept a per-request voice yet: `VoiceTTSRequest` carries
 * only `text`, and the provider/voice come from the process-level env vars
 * `VOICE_TTS_PROVIDER` / `VOICE_TTS_VOICE`, read once at import. So a selection
 * made here is sent but ignored until the backend reads it — changing the voice
 * today still means editing env and restarting the voice server. The UI says so
 * plainly; see the note in FlowControls.
 *
 * ── Why the voice lists are short ────────────────────────────────────────────
 * Only voice IDs that are verifiable are listed: each adapter's own documented
 * default, plus OpenAI's published voice set. Cartesia identifies voices by
 * opaque UUID and Inworld/Deepgram by catalogue names that aren't in this repo —
 * guessing those would produce IDs that fail at the provider, so instead every
 * provider takes a free-text ID pasted from its own playground.
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
    id: 'cartesia',
    label: 'Cartesia',
    voices: [{ id: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4', label: 'Adapter default' }],
    browseAt: 'play.cartesia.ai',
  },
  {
    id: 'inworld',
    label: 'Inworld',
    voices: [{ id: 'Ashley', label: 'Ashley (default)' }],
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
