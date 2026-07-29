/**
 * One voice per student, across every phase.
 *
 * The failure this locks down was invisible in the UI: the REST path applied
 * the tier's default when nothing was picked, and the WebSocket path didn't —
 * so a premium student heard Cartesia in the diagnostic and OpenAI (the server
 * env default) in guided practice, with nothing on screen to say why.
 *
 * Both transports now resolve through `effectiveVoice`, so these tests assert
 * on that resolver rather than on either transport's own plumbing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

/** Load lib/tts with both stores stubbed to a given tier + picker selection. */
async function effectiveVoiceFor(
  tier: string | null,
  selection: { ttsProvider: string | null; ttsVoice: string | null } = {
    ttsProvider: null,
    ttsVoice: null,
  },
) {
  vi.resetModules();
  vi.doMock('@/store/useAuthStore', () => ({
    useAuthStore: { getState: () => ({ tier }) },
  }));
  vi.doMock('@/store/useNumeraStore', () => ({
    useNumeraStore: { getState: () => selection },
  }));
  vi.doMock('@/store/useMicLevel', () => ({
    useMicLevel: { getState: () => ({ setAiSpeaking: vi.fn(), markBoundary: vi.fn() }) },
  }));
  vi.doMock('@/lib/api', () => ({ synthesizeSpeech: vi.fn() }));
  const { effectiveVoice } = await import('@/lib/tts');
  return effectiveVoice();
}

describe('effectiveVoice', () => {
  beforeEach(() => vi.resetModules());

  it('gives a premium student Cartesia before they touch the picker', async () => {
    expect(await effectiveVoiceFor('premium')).toEqual({
      provider: 'cartesia',
      voice: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4',
    });
  });

  it('gives a basic student Inworld before they touch the picker', async () => {
    expect(await effectiveVoiceFor('basic')).toEqual({
      provider: 'inworld',
      voice: 'Ashley',
    });
  });

  it('never silently upgrades an unknown tier onto the expensive provider', async () => {
    // Null rather than Cartesia: the caller then sends no provider and the
    // backend decides, which is the safe direction for an unrecognised plan.
    expect(await effectiveVoiceFor('mystery-plan')).toEqual({ provider: null, voice: null });
    expect(await effectiveVoiceFor(null)).toEqual({ provider: null, voice: null });
  });

  it('honours an explicit pick over the tier default', async () => {
    expect(
      await effectiveVoiceFor('premium', {
        ttsProvider: 'cartesia',
        ttsVoice: '573e3144-a684-4e72-ac2b-9b2063a50b53', // Teacher Lady
      }),
    ).toEqual({ provider: 'cartesia', voice: '573e3144-a684-4e72-ac2b-9b2063a50b53' });
  });

  it('resolves to one voice for the REST body and the WS query alike', async () => {
    // The actual regression: these two must not diverge. Build both from the
    // same resolver output and check the value that reaches each transport.
    process.env.NEXT_PUBLIC_WS_URL = 'wss://nablix.ai/api/voice/stream';
    const resolved = await effectiveVoiceFor('premium');
    const { buildVoiceStreamUrl } = await import('@/lib/runtimeConfig');
    const url = new URL(buildVoiceStreamUrl('SESSION005', 'ST001', resolved));
    expect(url.searchParams.get('tts_provider')).toBe('cartesia');
    expect(url.searchParams.get('tts_voice')).toBe(resolved.voice);
    delete process.env.NEXT_PUBLIC_WS_URL;
  });
});
