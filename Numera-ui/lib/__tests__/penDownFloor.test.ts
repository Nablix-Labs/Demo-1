/**
 * Pen-down must not strand the student's microphone.
 *
 * The bug this pins was student-fatal and silent. `setStudentWriting(true)`
 * (pen-down, §1 "remain silent while the student writes") calls
 * `stopTutorSpeech()`, which on the server transport hard-stops the audio
 * stream WITHOUT firing onIdle — and onIdle is the only thing that reopens the
 * student's turn there. So `voiceStatus` stayed at 'speaking' with nothing
 * playing, and because app/page.tsx gates `setTransmitting` on
 * `voiceStatus === 'listening'`, the student's audio stopped being SENT for the
 * rest of the session. An open mic going nowhere.
 *
 * Tapping "Check my work" did not recover it either — submitCanvasWork never
 * touches voiceStatus.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/lib/tts', () => ({
  speakTutor: vi.fn(),
  stopTutorSpeech: vi.fn(),
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');
const {
  setStudentWriting, setPenDown, isPenDown, resetTutorSpeech,
} = await import('@/lib/tutorSpeech');

const status = () => useNumeraStore.getState().voiceStatus;

beforeEach(() => {
  resetTutorSpeech();
  useNumeraStore.setState({ voiceStatus: 'idle', currentTurnId: null });
});

describe('pen-down while the tutor is speaking', () => {
  it('hands the turn back instead of stranding it on "speaking"', () => {
    useNumeraStore.setState({ voiceStatus: 'speaking' });
    setStudentWriting(true);
    expect(status()).toBe('listening');
    // A turn id is minted too — the socket subscribes to that to re-send turn
    // context, which the server needs before the student's next utterance.
    expect(useNumeraStore.getState().currentTurnId).toBeTruthy();
  });

  it('does not touch a turn the server is still working on', () => {
    // Reopening from 'processing' would abandon a reply in flight.
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
