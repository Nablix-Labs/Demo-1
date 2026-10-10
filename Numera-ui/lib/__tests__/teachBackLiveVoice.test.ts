import { afterEach, describe, expect, it, vi } from 'vitest';
import { TeachBackVoiceConnection, isOnlyFiller, speakRequest, transcriptConfidence, type TeachBackVoiceEvents } from '@/lib/teachback/realtimeVoice';

const session = {
  client_secret: 'ek_test', calls_url: 'https://example.test/calls', response_timeout_seconds: 45,
  request_retry_count: 1, speaker_instructions: 'Say only the words in <say>.',
  filler_words: ['um', 'uh', 'okay', 'so', 'hmm'],
};

function liveVoice() {
  const track = { enabled: false, stop: vi.fn() };
  const sent: Array<Record<string, unknown>> = [];
  const channel = {
    readyState: 'open', onmessage: null as ((e: { data: string }) => void) | null, onclose: null as (() => void) | null,
    send: (raw: string) => sent.push(JSON.parse(raw)), close: vi.fn(),
  };
  const peer = { connectionState: 'connected', onconnectionstatechange: null, close: vi.fn() };
  const microphone = { getAudioTracks: () => [track], getTracks: () => [track] };
  const events: TeachBackVoiceEvents = { onHeard: vi.fn(), onTranscript: vi.fn(), onClosed: vi.fn() };
  // The constructor is private; connect() needs a real browser, so build it around fakes.
  const Connection = TeachBackVoiceConnection as unknown as new (...args: unknown[]) => TeachBackVoiceConnection;
  const voice = new Connection(peer, channel, microphone, { srcObject: null }, session, events);
  const receive = (event: Record<string, unknown>) => channel.onmessage?.({ data: JSON.stringify(event) });
  return { voice, track, sent, channel, events, receive };
}

afterEach(() => { vi.useRealTimers(); });

describe('Live voice hears the student', () => {
  it('opens the mic for the student, closes it when turn detection ends the turn, and hands over the transcript', () => {
    const { voice, track, sent, events, receive } = liveVoice();
    voice.listen();
    expect(track.enabled).toBe(true);
    expect(sent).toContainEqual({ type: 'input_audio_buffer.clear' });

    receive({ type: 'conversation.item.input_audio_transcription.delta', item_id: 'item-1', delta: 'n plus ' });
    receive({ type: 'conversation.item.input_audio_transcription.delta', item_id: 'item-1', delta: 'four' });
    expect(events.onHeard).toHaveBeenLastCalledWith('n plus four');

    receive({ type: 'input_audio_buffer.committed', item_id: 'item-1' });
    expect(track.enabled).toBe(false);

    receive({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'item-1',
      transcript: ' The starting number changes. ', logprobs: [{ logprob: -0.1 }, { logprob: -0.3 }] });
    expect(events.onTranscript).toHaveBeenCalledWith('The starting number changes.', Math.exp(-0.2));
    expect(sent).toContainEqual({ type: 'conversation.item.delete', item_id: 'item-1' });
    expect(events.onHeard).toHaveBeenLastCalledWith('');
  });

  it('listens again after silence or a failed transcription instead of sending an empty turn', () => {
    const { voice, track, events, receive } = liveVoice();
    receive({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'item-1', transcript: '  ' });
    expect(events.onTranscript).not.toHaveBeenCalled();
    expect(track.enabled).toBe(true);
    voice.pause();
    receive({ type: 'conversation.item.input_audio_transcription.failed', item_id: 'item-2', error: { message: 'bad audio' } });
    expect(track.enabled).toBe(true);
    expect(events.onTranscript).not.toHaveBeenCalled();
  });
});

describe('Live voice ignores thinking out loud', () => {
  it('keeps listening instead of sending a turn made only of fillers', () => {
    const { voice, track, events, receive } = liveVoice();
    voice.pause();
    receive({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'item-1', transcript: 'Okay, so... um.' });
    expect(events.onTranscript).not.toHaveBeenCalled();
    expect(track.enabled).toBe(true);
    receive({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'item-2', transcript: 'Okay so n changes.' });
    expect(events.onTranscript).toHaveBeenCalledWith('Okay so n changes.', null);
  });

  it('only treats a turn as filler when every word is one', () => {
    const fillers = session.filler_words;
    expect(isOnlyFiller('Um, hmm.', fillers)).toBe(true);
    expect(isOnlyFiller('so 4', fillers)).toBe(false);
    expect(isOnlyFiller('so the letter', fillers)).toBe(false);
    expect(isOnlyFiller('', fillers)).toBe(false);
  });
});

describe('Live voice speaks only the approved reply', () => {
  it('asks Realtime to say the exact words with no conversation and keeps the mic shut until playback ends', async () => {
    const { voice, track, sent, receive } = liveVoice();
    voice.listen();
    let finished = false;
    const speaking = voice.speak('I follow that n changes. Can you teach me what stays fixed?').then(() => { finished = true; });
    expect(track.enabled).toBe(false);
    expect(sent.at(-1)).toEqual(speakRequest(session.speaker_instructions, 'I follow that n changes. Can you teach me what stays fixed?'));
    voice.listen();
    expect(track.enabled).toBe(false);

    receive({ type: 'response.done', response: { status: 'completed' } });
    await Promise.resolve();
    expect(finished).toBe(false);
    receive({ type: 'output_audio_buffer.stopped' });
    await speaking;
    voice.listen();
    expect(track.enabled).toBe(true);
  });

  it('never stalls the lesson when playback never reports its end', async () => {
    vi.useFakeTimers();
    const { voice, receive } = liveVoice();
    let finished = false;
    void voice.speak('I follow.').then(() => { finished = true; });
    receive({ type: 'response.done', response: { status: 'completed' } });
    await vi.advanceTimersByTimeAsync(4_000);
    expect(finished).toBe(true);
  });

  it('stops talking when the student cuts in, and ends on a failed response', async () => {
    const { voice, sent, receive } = liveVoice();
    const first = voice.speak('A long reply.');
    voice.stopSpeaking();
    await first;
    expect(sent).toContainEqual({ type: 'response.cancel' });
    const second = voice.speak('Another reply.');
    receive({ type: 'response.done', response: { status: 'failed' } });
    await second;
  });
});

describe('Live voice connection', () => {
  it('tells the screen once when the connection drops and releases the mic', () => {
    const { voice, track, channel, events } = liveVoice();
    channel.onclose?.();
    voice.close();
    expect(events.onClosed).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalled();
  });

  it('turns transcription log-probabilities into the confidence the backend checks', () => {
    expect(transcriptConfidence([{ logprob: 0 }])).toBe(1);
    expect(transcriptConfidence([])).toBeNull();
    expect(transcriptConfidence([{ logprob: 0.5 }])).toBeNull();
    expect(transcriptConfidence(undefined)).toBeNull();
  });
});
