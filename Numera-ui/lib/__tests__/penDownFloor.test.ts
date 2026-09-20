/**
 * Pen-down must not strand the student's microphone.
 *
 * The bug this pins was student-fatal and silent. `setStudentWriting(true)`
 * (pen-down, §1 "remain silent while the student writes") used to call
 * `stopTutorSpeech()`, which on the server transport hard-stops the audio
 * stream WITHOUT firing onIdle — and onIdle is the only thing that reopens the
 * student's turn there. So `voiceStatus` stayed at 'speaking' with nothing
 * playing, and because app/page.tsx gates `setTransmitting` on
 * `voiceStatus === 'listening'`, the student's audio stopped being SENT for the
 * rest of the session. An open mic going nowhere.
 *
 * Tapping "Check my work" did not recover it either — submitCanvasWork never
 * touches voiceStatus.
 *
 * It was fixed then by reopening the turn explicitly after the hard stop. Since
 * #305 the hard stop is gone entirely — pen-down lets the line finish — so the
 * stream reaches onIdle by itself and the ordinary path reopens the turn. These
 * now pin the thing that keeps that true: pen-down must not kill the stream.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

const stopTutorSpeech = vi.fn();
vi.mock('@/lib/tts', () => ({
  speakTutor: vi.fn(),
  stopTutorSpeech: () => stopTutorSpeech(),
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');
const {
  setStudentWriting, setPenDown, isPenDown, resetTutorSpeech,
} = await import('@/lib/tutorSpeech');

const status = () => useNumeraStore.getState().voiceStatus;

beforeEach(() => {
  stopTutorSpeech.mockClear();
  resetTutorSpeech();
  useNumeraStore.setState({ voiceStatus: 'idle', currentTurnId: null });
});

describe('pen-down while the tutor is speaking', () => {
  it('never hard-stops the stream — that is what stranded the mic', () => {
    useNumeraStore.setState({ voiceStatus: 'speaking' });
    setStudentWriting(true);
    expect(stopTutorSpeech).not.toHaveBeenCalled();
  });

  it('leaves the turn on "speaking", because the tutor really is still speaking', () => {
    // Reopening here would be a lie about the channel and would race the
    // onIdle that is still coming when the line lands. Half-duplex holds.
    useNumeraStore.setState({ voiceStatus: 'speaking' });
    setStudentWriting(true);
    expect(status()).toBe('speaking');
  });

  it('does not touch a turn the server is still working on', () => {
    useNumeraStore.setState({ voiceStatus: 'processing' });
    setStudentWriting(true);
    expect(status()).toBe('processing');
  });

  it('does not mint a fresh turn on every stroke while already listening', () => {
    useNumeraStore.setState({ voiceStatus: 'listening', currentTurnId: 'T-1' });
    setStudentWriting(true);
    expect(useNumeraStore.getState().currentTurnId).toBe('T-1');
  });
});

describe('pen state is tracked apart from the floor', () => {
  it('follows pointer down and up', () => {
    expect(isPenDown()).toBe(false);
    setPenDown(true);
    expect(isPenDown()).toBe(true);
    setPenDown(false);
    // The floor is NOT handed back on pen-up — unsubmitted work still holds it.
    expect(isPenDown()).toBe(false);
  });

  it('resets on teardown', () => {
    setPenDown(true);
    resetTutorSpeech();
    expect(isPenDown()).toBe(false);
  });
});
