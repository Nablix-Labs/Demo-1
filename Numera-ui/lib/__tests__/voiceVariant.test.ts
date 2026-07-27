/**
 * Tutor voice variant — the two places a selection has to reach the backend.
 *
 * Both are inert until the backend reads them (see lib/voiceOptions.ts), which is
 * exactly why they need locking down: nothing observable breaks if they silently
 * stop being sent, so a regression here would only surface much later, as
 * "changing the voice does nothing" long after the backend added support.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('buildVoiceStreamUrl', () => {
  beforeEach(() => {
    vi.resetModules();
    process.env.NEXT_PUBLIC_WS_URL = 'wss://nablix.ai/api/voice/stream';
  });
  afterEach(() => {
    delete process.env.NEXT_PUBLIC_WS_URL;
  });

  it('carries the selected provider and voice as query params', async () => {
    const { buildVoiceStreamUrl } = await import('@/lib/runtimeConfig');
    const url = new URL(
      buildVoiceStreamUrl('SESSION005', { provider: 'cartesia', voice: 'abc-123' }),
    );
    expect(url.searchParams.get('tts_provider')).toBe('cartesia');
    expect(url.searchParams.get('tts_voice')).toBe('abc-123');
    // The session param the server actually reads must survive alongside them.
    expect(url.searchParams.get('session')).toBe('SESSION005');
  });

  it('omits both params when nothing is selected, leaving the URL unchanged', async () => {
    const { buildVoiceStreamUrl } = await import('@/lib/runtimeConfig');
    const plain = buildVoiceStreamUrl('SESSION005');
    const withNulls = buildVoiceStreamUrl('SESSION005', { provider: null, voice: null });
    expect(plain).toBe(withNulls);
    expect(plain).not.toContain('tts_provider');
    expect(plain).not.toContain('tts_voice');
  });
});

describe('synthesizeSpeech payload', () => {
  beforeEach(() => vi.resetModules());

  /** Capture the body POSTed to /voice/tts without a network call. Resets the
   *  module graph per call so each invocation gets its own axios mock — without
   *  it a second call in the same test reuses the first call's cached client. */
  async function postBodyFor(opts?: { provider?: string | null; voice?: string | null }) {
    vi.resetModules();
    const post = vi.fn().mockResolvedValue({ data: { audio_base64: null } });
    vi.doMock('axios', () => ({
      default: { create: () => ({ post, interceptors: { request: { use: vi.fn() } } }) },
    }));
    const { synthesizeSpeech } = await import('@/lib/api');
    await synthesizeSpeech('hello', opts);
    return post.mock.calls[0][1];
  }

  it('sends the selected provider and voice alongside the text', async () => {
    expect(await postBodyFor({ provider: 'inworld', voice: 'Ashley' })).toEqual({
      text: 'hello',
      provider: 'inworld',
      voice: 'Ashley',
    });
  });

  it('sends text alone when nothing is selected, so the default request is unchanged', async () => {
    expect(await postBodyFor({ provider: null, voice: null })).toEqual({ text: 'hello' });
    expect(await postBodyFor()).toEqual({ text: 'hello' });
  });
});
