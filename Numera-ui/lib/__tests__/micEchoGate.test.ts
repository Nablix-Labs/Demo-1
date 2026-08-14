import { describe, it, expect } from 'vitest';

/**
 * The mic must be shut whenever the tutor is making sound.
 *
 * Manjusha, 4 Aug: "long sentences are broken to many and answers are generated
 * individually finally overlapping". The cause was the server transport gating
 * the mic on mute alone — so the tutor's audio went out of the speakers, back in
 * through the microphone, and Deepgram transcribed it as student speech.
 * UtteranceEnd then fired on the tutor's own words and produced another answer.
 *
 * The gate below is the exact expression from app/page.tsx. Kept as a pure
 * function so every state combination is checkable without a browser.
 */
function micIsLive(s: {
  micMuted: boolean;
  voiceStatus: 'idle' | 'listening' | 'speaking' | 'processing' | 'waiting';
  tutorSpeaking: boolean;
}): boolean {
  return !s.micMuted && s.voiceStatus === 'listening' && !s.tutorSpeaking;
}

const base = { micMuted: false, voiceStatus: 'listening' as const, tutorSpeaking: false };

describe('the tutor can never hear itself', () => {
  it('mic is live when the student has the floor', () => {
    expect(micIsLive(base)).toBe(true);
  });

  it('mic is shut while tutor audio is playing', () => {
    expect(micIsLive({ ...base, tutorSpeaking: true })).toBe(false);
  });

  it('mic is shut from the moment the reply lands, before audio starts', () => {
    // The window between tutor_response arriving and the first audio chunk
    // playing is seconds long. Leaving the mic open across it let the mic catch
    // the tutor's opening words.
    expect(micIsLive({ ...base, voiceStatus: 'speaking', tutorSpeaking: false })).toBe(false);
  });

  it('mic is shut while a request is in flight', () => {
    expect(micIsLive({ ...base, voiceStatus: 'processing' })).toBe(false);
  });

  it('mic is shut when parked after the final turn', () => {
    expect(micIsLive({ ...base, voiceStatus: 'waiting' })).toBe(false);
  });

  it('mute always wins, whatever the turn state', () => {
    for (const voiceStatus of ['idle', 'listening', 'speaking', 'processing', 'waiting'] as const) {
      for (const tutorSpeaking of [true, false]) {
        expect(micIsLive({ micMuted: true, voiceStatus, tutorSpeaking })).toBe(false);
      }
    }
  });

  it('needs BOTH signals clear — either one alone keeps it shut', () => {
    expect(micIsLive({ ...base, voiceStatus: 'speaking', tutorSpeaking: true })).toBe(false);
    expect(micIsLive({ ...base, voiceStatus: 'speaking' })).toBe(false);
    expect(micIsLive({ ...base, tutorSpeaking: true })).toBe(false);
  });

  it('reopens once the tutor is genuinely finished', () => {
    // beginListeningTurn() sets voiceStatus back to listening; finish() clears
    // aiSpeaking. Both happen in the same funnel, so this is the only state the
    // mic can come back in.
    expect(micIsLive({ micMuted: false, voiceStatus: 'listening', tutorSpeaking: false })).toBe(true);
  });
});
