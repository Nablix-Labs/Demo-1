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

  it('gives a premium student Inworld before they touch the picker', async () => {
    // 31 Jul (Manjusha): Inworld is the product voice for EVERY tier —
    // Cartesia ran out of credits twice in four days at ~7.5x the price.
    expect(await effectiveVoiceFor('premium')).toEqual({
      provider: 'inworld',
      voice: 'Ashley',
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

  it('honours an explicit pick over the tier default — within the offered provider', async () => {
    expect(
      await effectiveVoiceFor('premium', {
        ttsProvider: 'inworld',
        ttsVoice: 'Olivia',
      }),
    ).toEqual({ provider: 'inworld', voice: 'Olivia' });
  });

  it('resolves to one voice for the REST body and the WS query alike', async () => {
    // The actual regression: these two must not diverge. Build both from the
    // same resolver output and check the value that reaches each transport.
    process.env.NEXT_PUBLIC_WS_URL = 'wss://nablix.ai/api/voice/stream';
    const resolved = await effectiveVoiceFor('premium');
    const { buildVoiceStreamUrl } = await import('@/lib/runtimeConfig');
    const url = new URL(buildVoiceStreamUrl('SESSION005', 'ST001', resolved));
    expect(url.searchParams.get('tts_provider')).toBe('inworld');
    expect(url.searchParams.get('tts_voice')).toBe(resolved.voice);
    delete process.env.NEXT_PUBLIC_WS_URL;
  });
});

/** Load lib/tts with stubbed stores and return its full module surface. */
async function ttsModuleFor(
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
  return import('@/lib/tts');
}

describe('product-voice degradation (Cartesia quota outage, 31 Jul)', () => {
  it('speaks as Inworld while Cartesia is degraded — not a robot, not OpenAI', async () => {
    const tts = await ttsModuleFor('premium');
    tts.markProviderDegraded('cartesia');
    expect(tts.effectiveVoice()).toEqual({ provider: 'inworld', voice: 'Ashley' });
  });

  it('brings the real voice back after the recovery window (a top-up heals itself)', async () => {
    const tts = await ttsModuleFor('premium');
    tts.markProviderDegraded('inworld', Date.now() - 5 * 60_000 - 1);
    expect(tts.effectiveVoice().provider).toBe('inworld');
  });

  it('degrades basic-tier Inworld onto Cartesia, symmetric', async () => {
    const tts = await ttsModuleFor('basic');
    tts.markProviderDegraded('inworld');
    expect(tts.effectiveVoice().provider).toBe('cartesia');
  });

  it('never degrades onto anything outside the two product voices', async () => {
    const tts = await ttsModuleFor('premium');
    tts.markProviderDegraded('openai'); // not a product voice — must be a no-op
    expect(tts.effectiveVoice()).toEqual({ provider: 'inworld', voice: 'Ashley' });
  });

  it('an explicit picker choice on the degraded provider still degrades', async () => {
    // Teacher Lady is a Cartesia voice; if Cartesia is down her audio cannot
    // exist, so the session speaks Inworld until recovery rather than robot.
    const tts = await ttsModuleFor('premium', {
      ttsProvider: 'cartesia',
      ttsVoice: '573e3144-a684-4e72-ac2b-9b2063a50b53',
    });
    tts.markProviderDegraded('cartesia');
    expect(tts.effectiveVoice()).toEqual({ provider: 'inworld', voice: 'Ashley' });
  });
});

describe('stale picker selections after the 31 Jul Inworld switch', () => {
  it('ignores a persisted Cartesia pick now that no tier offers Cartesia', async () => {
    // Real case: testers had "Teacher Lady" (Cartesia) persisted from the
    // picker; honouring it kept them on the credit-dead provider forever.
    const tts = await ttsModuleFor('premium', {
      ttsProvider: 'cartesia',
      ttsVoice: '573e3144-a684-4e72-ac2b-9b2063a50b53',
    });
    expect(tts.effectiveVoice()).toEqual({ provider: 'inworld', voice: 'Ashley' });
  });

  it('still honours a picker choice within the offered provider', async () => {
    const tts = await ttsModuleFor('premium', { ttsProvider: 'inworld', ttsVoice: 'Olivia' });
    expect(tts.effectiveVoice()).toEqual({ provider: 'inworld', voice: 'Olivia' });
  });
});
